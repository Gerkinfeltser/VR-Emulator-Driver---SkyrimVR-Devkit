// Run from a VS 2022 x64 developer shell:
// cl /nologo /std:c++17 /EHsc /MT /I. tests/grip_input_check.cpp /link user32.lib
// Then run grip_input_check.exe. This check uses anonymous memory and never injects desktop input.
#include "../devkit_input.h"
#include <cassert>
#include <iostream>


int main()
{
    using namespace DevkitInput;
    Pose head;
    Shared& poseState = S();
    poseState.pose = head;
    // Initial snapshots must honor configured angles before any controls file refresh.
    for (bool hand : { false, true }) {
        const auto& settings = hand ? poseState.rightController : poseState.leftController;
        double w, x, y, z;
        ControllerRotation(settings, w, x, y, z);
        const Pose actual = ControllerSnapshot(hand);
        assert(std::abs(actual.ow - w) < 1e-9 && std::abs(actual.ox - x) < 1e-9
            && std::abs(actual.oy - y) < 1e-9 && std::abs(actual.oz - z) < 1e-9);
    }
    poseState.leftController = { -0.20, -0.35, -0.40, 0, 0, 0 };
    ControllerRotation(poseState.leftController, poseState.leftRotation[0], poseState.leftRotation[1],
        poseState.leftRotation[2], poseState.leftRotation[3]);
    head.px = 1; head.py = 2; head.pz = 3;
    head.ow = std::cos(3.14159265358979323846 / 4);
    head.oy = std::sin(3.14159265358979323846 / 4);
    poseState.pose = head;
    Pose left = ControllerSnapshot(false);
    assert(std::abs(left.px - 0.6) < 1e-9 && std::abs(left.pz - 3.2) < 1e-9);
    ControllerPoseSettings zero = { 0, 0, 0, 0, 0, 0 };
    poseState.leftController = zero;
    left = ControllerSnapshot(false);
    assert(left.px == head.px && left.py == head.py && left.pz == head.pz && left.ow == head.ow && left.oy == head.oy);
    ControllerPoseSettings composed = { 0, 0, 0, 90, 90, 0 };
    double cw, cx, cy, cz;
    ControllerRotation(composed, cw, cx, cy, cz);
    assert(std::abs(cx - 0.5) < 1e-9 && std::abs(cy - 0.5) < 1e-9 && std::abs(cz + 0.5) < 1e-9);
    poseState.leftController = { 0, 0, 0, 90, 90, 90 };
    ControllerRotation(poseState.leftController, poseState.leftRotation[0], poseState.leftRotation[1],
        poseState.leftRotation[2], poseState.leftRotation[3]);
    left = ControllerSnapshot(false);
    assert(std::abs(left.ow - 0.5) < 1e-9 && std::abs(left.ox - 0.5) < 1e-9
        && std::abs(left.oy - 0.5) < 1e-9 && std::abs(left.oz + 0.5) < 1e-9);

    Shared state;
    Keys keys;
    keys.buttonMappingValid = true;
    keys.buttonWord = kRightGripBit;
    Step(state, keys, 0.0);
    assert(state.rightGripRaw && !state.rightGrip); // A held F23 at startup is not liveness.
    keys.heartbeat = true;
    Step(state, keys, 0.1);
    assert(state.rightGrip);
    keys.buttonWord = 0;
    Step(state, keys, 0.2);
    assert(!state.rightGrip && state.rightGripEverSeen);
    keys.buttonWord = kRightGripBit;
    Step(state, keys, 0.3);
    assert(state.rightGrip);
    Step(state, keys, 0.6);
    assert(!state.rightGrip && state.rightGripRaw); // F23 expiry clears a stuck mapped hold.
    keys.heartbeat = false;
    Step(state, keys, 0.7);
    assert(state.rightGrip);
    keys.buttonMappingValid = false;
    Step(state, keys, 0.8);
    assert(!state.rightGrip && !state.rightGripRaw);
    keys.buttonMappingValid = true;
    keys.buttonWord = 1u << 2; // Left Grip must not press Right Grip at this checkpoint.
    Step(state, keys, 0.9);
    assert(!state.rightGrip);
    keys.buttonWord = kRightGripBit;
    keys.heartbeat = true;
    Step(state, keys, 1.0);
    assert(state.rightGrip); // No second freshness timer or publisher phase is required.

    double t = 1.0;
    const unsigned leftBits = kLeftTrackpadClickBit | kLeftTrackpadTouchBit;
    for (unsigned combination = 0; combination != 8; ++combination) {
        keys.buttonWord = ((combination & 1) ? kLeftTrackpadClickBit : 0)
                        | ((combination & 2) ? kLeftTrackpadTouchBit : 0)
                        | ((combination & 4) ? kRightGripBit : 0);
        keys.heartbeat = !keys.heartbeat;
        t += 0.1;
        Step(state, keys, t);
        assert(state.leftTrackpad == (keys.buttonWord & leftBits));
        assert(state.rightGrip == ((combination & 4) != 0));
    }
    assert(state.leftTrackpadEverSeen == leftBits);
    Step(state, keys, t + 0.5);
    assert(state.leftTrackpad == 0 && !state.rightGrip);
    assert(state.leftTrackpadRaw == leftBits); // Timeout releases both while retaining raw/history.
    keys.heartbeat = !keys.heartbeat;
    keys.buttonMappingValid = false;
    Step(state, keys, t + 0.6);
    assert(state.leftTrackpadRaw == 0 && state.leftTrackpad == 0 && !state.rightGrip);

    // The original right Interact sequence remains independent of shared left-hand input.
    keys.interact = true;
    Step(state, keys, t + 0.61);
    assert(state.trackpadTouch && !state.trackpadClick && state.leftTrackpad == 0);
    Step(state, keys, t + 0.63);
    assert(state.trackpadTouch && state.trackpadClick && state.leftTrackpad == 0);
    Step(state, keys, t + 0.74);
    assert(!state.trackpadTouch && !state.trackpadClick && state.leftTrackpad == 0);

    ButtonMapping reader;
    reader.handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(LONG), nullptr);
    assert(reader.handle);
    reader.view = static_cast<volatile LONG*>(MapViewOfFile(reader.handle, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, sizeof(LONG)));
    assert(reader.view);
    unsigned word = 99;
    InterlockedExchange(reader.view, static_cast<LONG>(kRightGripBit));
    assert(reader.Read(0, word) && word == kRightGripBit);
    for (unsigned bit = 28; bit != 32; ++bit) {
        InterlockedExchange(reader.view, static_cast<LONG>(kRightGripBit | (1u << bit)));
        assert(!reader.Read(0, word) && word == 0); // All four reserved bits fail released.
    }
    InterlockedExchange(reader.view, 0);
    assert(reader.Read(0, word) && word == 0);
    reader.Close();
    reader.nextOpen = 100; // Model an absent mapping without touching the production named object.
    assert(!reader.Read(1, word) && word == 0);
    std::cout << "PASS: Controller transform invariants, grip/left click-touch, F23 timing, and reserved-bit rejection\n";
}
