# Ghost Dashboard Design Manifesto 👻 (GHOST_OS Edition)

## Visual Identity: "GHOST_OS Stealth"
The Ghost Dashboard has evolved into a high-contrast, "Stealth-Ops" interface. It mimics a low-level system terminal (OS) while maintaining the elegance of a mission control center.

### Typography
- **Headlines/UI:** `Inter` (Sans-serif) - Focused on maximum legibility at small sizes.
- **Data/Logs:** `JetBrains Mono` (Monospace) - Used for mission objectives, timestamps, and system logs to evoke a technical, "under-the-hood" feel.

### Color Palette (GHOST_OS System Colors)
- **Primary Background:** `#0a0a0c` (ghost-900) - Deep void for stealth.
- **Surface Elevation:** `#121214` (ghost-800) / `#1a1a1a` (chrome-surface).
- **Core Accent:** `#D4AF37` (**Gold Accent**) - Used for high-priority mission data, active indicators, and branding.
- **Vibe Pulse:** `#d946ef` (**Ghost Vibe Magenta**) - Retained for message bubbles and personal identity.
- **System Green:** `#22c55e` (status-pulse) - Real-time link stability and Auto-Pilot status.

### Component Design & Effects
- **Chrome Reflect:** A 145-degree linear gradient (`#1a1a1a` to `#0a0a0c`) with an inset white highlight for a metallic, hardware-like surface.
- **Gold Glow:** Subtle `rgba(212, 175, 55, 0.4)` text-shadow used on active ghost names to indicate "power-on" state.
- **Material Symbols:** Light-weight (300) icon set for a clean, futuristic navigation bar.

## Current Architecture (In Transition)
*Note: We are currently applying the GHOST_OS skin to the existing layout before a full structural overhaul.*

### 1. MISSION_CONTROL Sidebar
- Displays active "Ghosts" (chats).
- Features the `GHOST_LINK_STABLE` heartbeat indicator.

### 2. INTERACTION_CONSOLE
- Central message stream utilizing the **Chrome Reflect** background for incoming messages.
- User messages leverage the **Gold Accent** for a high-command visual priority.

### 3. MISSION_OBJECTIVE Header
- Glassmorphic overlay allowing the user to steer the AI's goal via the `AUTONOMY_LEVEL` toggles.

## Interaction Principles
- **Stealth First:** UI elements remain dim or grayscale until hovered or active.
- **High Information Density:** Uses small, monospace labels (10px) to provide maximum system context without cluttering the screen.

---
*VibeTexting V2.0 - GHOST_OS Core Update*
