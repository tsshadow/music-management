# Radio and Sync Mode: Host/Follower Model

## Overview
To provide a robust synchronization experience, we use a **Host/Follower** model for music playback. This avoids "fighting" for the progress bar and ensures smooth playback for the designated Lead client.

## Synchronization Modes

1. **Off (`'off'`)**:
   - The player operates purely locally.
   - No state is pushed to or pulled from the server's play queue.

2. **Host (`'host'`)**:
   - **Authoritative/Lead Mode**.
   - Periodically pushes the full state (`playlist`, `currentTrack`, `playing`, `position`) to the server.
   - Periodically pulls state to detect remote commands.
   - **Conflict Resolution**: If the server's `currentTrack` or `playing` state changes (and it's different from local), the Host treats this as a remote command (e.g., from a Follower), applies it, and continues as the authority.

3. **Follower (`'follower'`)**:
   - **Remote/Listener Mode**.
   - Periodically pulls everything from the server.
   - **Never** pushes position periodically. This prevents latency from causing the Host's progress bar to jump back.
   - **Interaction**: Manual controls (Play/Pause, Next, Prev, Seek) trigger an immediate `savePlayQueue` push (without periodic position) to signal intent to the Host.

## UI Indicators
The sync button cycles through the states:
- **Grey**: Off
- **Green**: Host (Leading)
- **Blue**: Follower (Remote/Following)

## Leadership Logic
Users should manually designate one device as the **Host** (e.g., the PC connected to speakers) and others as **Followers** (e.g., phones used as remotes). While multiple Hosts can technically exist, they will compete for authority, so a single Host is recommended for the best experience.
