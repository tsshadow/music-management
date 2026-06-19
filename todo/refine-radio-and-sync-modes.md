---
sessionId: session-260619-115009-vddp
isActive: true
---

# Requirements

### Overview & Goals
The goal is to provide a more robust synchronization experience by introducing a **Host/Follower** model. This solves the "jumping" issue where multiple clients fighting for the progress bar causes stuttering. Instead of every client being equal, one client is designated as the **Host (Lead)**, and others as **Followers (Remote)**.

### Scope
- **In Scope**:
    - Introduction of a tri-state synchronization toggle (Off, Host, Follower).
    - Implementation of authoritative "Lead" logic (Host mode).
    - Implementation of command-based "Remote" logic (Follower mode).
    - Logic to allow Followers to control the Host via the server.
    - Visual feedback via button colors.
    - Documentation of the design.
- **Out of Scope**:
    - Server-side changes to the Subsonic API.
    - Real-time WebSockets (sticking to polling/Subsonic API).

### User Stories
- **As a host**, I want to be the one driving the music and progress for a shared session, so my playback is smooth.
- **As a remote user**, I want to see what's playing on the host and be able to skip tracks or pause without causing the music to jump for everyone.
- **As a listener**, I want to follow the music on another device (like a living room PC) using my phone as a remote.

# Technical Design

### Current Implementation
Currently, `radioMode` is a binary toggle. When on, it both pulls the play queue from the server and pushes local changes back. This can lead to "fighting" for control if multiple users have it active and are out of sync.

### Proposed Changes
We will implement a 3-state system for synchronization to ensure a single "Source of Truth" for the playback position:

1. **Off (`'off'`)**:
   - No `getPlayQueue` (pull) or `savePlayQueue` (push).
   - Player is purely local.

2. **Host (`'host'`)**:
   - **Authoritative mode**.
   - Periodically pushes full state (`current`, `playing`, `position`, `playlist`) to the server.
   - Periodically pulls state to detect if a Follower has sent a command (detected by checking if the server's `current` or `playing` state changed).
   - If a remote command is detected, the Host applies it and becomes the authority for the new track.

3. **Follower (`'follower'`)**:
   - **Remote/Listener mode**.
   - Periodically pulls everything from the server.
   - **Never** pushes position periodically (prevents jumps).
   - Interaction: Manual playback controls (Next/Prev/Seek) call `savePlayQueue` to send the "Intent" to the server.
   - Local audio can be toggled on or off (the Follower follows the Host's position).

### UI Design
- **Icon**: The existing radio/circle icon.
- **States & Colors**:
  - `Off`: Grey (`#b3b3b3`)
  - `Host`: Green/Brand (`#1db954`) - *Leading*
  - `Follower`: Blue (`#3d91ff`) - *Remote/Following*
- **Toggle Cycle**: `Off` -> `Host` -> `Follower` -> `Off`.

### Data Models / Contracts
The `syncMode` will be a string store in `store.js`:
```javascript
export const syncMode = writable('off'); // 'off', 'host', 'follower'
```

### Leadership Logic
The leadership is now explicitly defined by the user:
- **Host**: The current client is the leader. It dictates the playback timing.
- **Follower**: The current client is a remote. It waits for the server (Host) to provide timing.
- **Conflict Resolution**: If multiple clients are in `'host'` mode, they will still fight for position. Users should ensure only one device is designated as Host for a seamless experience.

# Testing

### Validation Approach
Verification will be done by simulating multiple clients (tabs) and checking their interactions.

### Key Scenarios
1. **Remote Control**:
   - Client A is **Host** (on PC).
   - Client B is **Follower** (on Phone).
   - Client B clicks "Next".
   - Client B updates the server with the next track ID.
   - Client A pulls the state, sees the track change, and skips.
   - Client B sees Client A's progress and follows.
2. **Listen Along**:
   - Client A is **Host**. Client B is **Follower**.
   - Both play audio.
   - Client A's local time is the authority. Client B's player syncs its `currentTime` to Client A's pushed position.
3. **Prevention of Jumps**:
   - Even if Client B (Follower) has slight latency, it never pushes its position, so it can't "pull back" the Host's progress bar.

# Delivery Steps

###   Step 1: Update syncMode states in store.js
Update the store to support the new synchronization model and ensure persistence.

- Modify `src/lms/ui/spotify-ui/src/lib/store.js` to replace `radioMode` (boolean) with `syncMode` (string).
- Set default value to `'off'`.
- Ensure the state is persisted in `localStorage`.

###   Step 2: Implement Host and Follower logic in Player.svelte
Implement the core logic for the authoritative Host and the command-based Follower.

- Update `src/lms/ui/spotify-ui/src/lib/Player.svelte`:
- Modify `pushRadioState` to:
    - Push everything (including position) periodically if in `'host'` mode.
    - Only push specific changes (no periodic position) if in `'follower'` mode.
- Modify `syncRadio` to:
    - Apply all server state if in `'follower'` mode.
    - For `'host'` mode, only apply changes if the server state is different from local (indicating a remote command).
- Ensure playback controls (Next/Prev/Seek) trigger an immediate push in both modes.

###   Step 3: Update Player UI and visual indicators
Refine the UI to reflect the new Host/Follower roles.

- Update the sync button to cycle through: Off -> Host (Green) -> Follower (Blue).
- Add tooltips to explain that Host is the "Source of Truth" and Follower is the "Remote/Listener".
- Ensure the visual progress bar remains responsive in both modes.

###   Step 4: Create todo/radio-and-sync-mode.md documentation
Document the model for future reference.

- Create `todo/radio-and-sync-mode.md`.
- Explain the logic: why only the Host pushes position, and how Followers send commands.

###   Step 5: Verify build and deployment
Ensure the changes are integrated and the deployment script works as expected.

- Run `./build_and_publish.sh` to build, push, and deploy the updated application.
- Verify that the deployment is successful on the remote server.
- Commit all changes including the new documentation.