# Jam and Sync Mode: Host/Follower Model

## Overview
To provide a robust synchronization experience, we use a **Host/Follower** model for music playback, often referred to as **Jam Mode**. This avoids "fighting" for the progress bar and ensures smooth playback for the designated Lead client.

## Synchronization (Jam) Modes

1. **Off (`'off'`)**:
   - The player operates purely locally.
   - No state is pushed to or pulled from the server's play queue.

2. **Host (`'host'`)**:
   - **Authoritative/Lead Mode (Host Jam)**.
   - Periodically pushes the full state (`playlist`, `currentTrack`, `playing`, `position`) to the server.
   - Periodically pulls state to detect remote commands.
   - **Conflict Resolution**: If the server's `currentTrack` or `playing` state changes (and it's different from local), the Host treats this as a remote command (e.g., from a Follower), applies it, and continues as the authority.

3. **Follower - Jam (Remote) (`'follower-jam'`)**:
   - **Remote Control Mode**.
   - No local audio is played.
   - The UI reflects the Host's current track and play/pause state.
   - **Interaction**: Manual controls (Play/Pause, Next, Prev, Seek) send commands to the Host via the server.

4. **Follower - Radio (Listener) (`'follower-radio'`)**:
   - **Listen Along Mode**.
   - Local audio is played and synchronized with the Host's position.
   - **Restriction**: Manual playback controls are disabled (the client "only follows").
   - Periodically pulls everything from the server.
   - **Never** pushes position or track changes.

## UI Indicators
The Jam button cycles through the states:
- **Grey**: Off
- **Green**: Host (Leading)
- **Blue**: Jam: Remote (Controller)
- **Purple**: Radio: Listener (Following)

## Leadership Logic
Users should manually designate one device as the **Host** (e.g., the PC connected to speakers). Others can join as **Jam Followers** to act as remotes (e.g., guests with phones) or **Radio Followers** to listen along in sync (e.g., another device in another room).
