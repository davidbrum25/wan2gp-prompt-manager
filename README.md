# Prompt Manager for Wan2GP

Browse your generated images and videos, inspect their embedded metadata, and send individual values back to the Media Generator with a single click — similar to reusing prompts and seeds in Midjourney-style workflows.

Works with **both images and videos** that contain WanGP generation metadata.

## Screenshot

Three-column layout with sidebar controls, thumbnail grid, and metadata preview (v1.4.0):

![Prompt Manager](screens/005.png)

## Features

### Three-column layout (v1.4.0)

- **Left sidebar (collapsible)** — view mode, add/remove custom folders, refresh, open outputs folder, library import/export, search, filters, sort, grid size, and bulk actions. Can be hidden using the collapse button (`◀`) at the top right of the sidebar.
- **Center grid** — thumbnail browser with folder navigation and adjustable zoom slider (persisted in your browser). Expands automatically when the sidebar is collapsed.
- **Right panel** — preview, clickable metadata, variations, library tags, and generation actions.

### Interactive Fullscreen View (v1.4.0)

- **Double-click to open** — double-click any thumbnail in the grid or the preview box in the detail panel to open native browser fullscreen.
- **Keyboard navigation** — press Arrow Left/Up or Arrow Right/Down (or click the on-screen glassmorphic `❮` / `❯` arrows) to cycle through the files in the grid.
- **Scroll wheel zoom** — scroll the mouse wheel over fullscreen images to zoom in and out smoothly (up to 10x).
- **Drag-to-pan** — click and drag the mouse when zoomed in to pan around the image naturally.
- **Background synchronization** — navigating in fullscreen automatically updates the active selection in the background grid, so the detail panel matches when you exit fullscreen.

### Custom Folders & Combined View (v1.4.0)

- **Register custom directories** — click the `➕` button in the sidebar to open your system's native scaled file browser (using Zenity / Tkinter) and add custom folders to the view list.
- **Delete custom directories** — click the `➖` button in the sidebar to remove registered custom folders (prompts for confirmation or choosing from a list of registered folders).
- **View switcher** — switch between default outputs, library, or specific custom directories in the `View` dropdown.
- **All Folders Combined View** — select `"All Folders"` from the View dropdown to display media from all registered folders (and default outputs) aggregated in a single combined view.
- **Persistent storage** — custom folder lists are saved locally to `custom_folders.json` and persist across restarts.

### Browse & filter

- Grid view of outputs from your configured save folders (with folder navigation)
- **Search** by prompt, model, filename, or tags
- **Filters** for model, media type (image/video), and date range
- **Sort** by newest, oldest, model name, or prompt length
- **Grid size** preset: Compact / Comfortable / Large, plus a **zoom slider** for fine-tuning thumbnail size
- Preview panel for the selected image or video
- **Open Outputs Folder** button (icon toolbar in sidebar)

### Click-to-apply metadata

- **Model**
- **Prompt**
- **Seed**
- **Resolution**
- **Steps**
- **CFG**
- **LoRAs**
- **Copy to clipboard** (📋) on any metadata row

Partial field clicks apply to your **current** model. Clicking **Model** switches to the model used in that generation. **Use All Settings** loads the complete configuration from the file.

### Variations & generation

- **Recreate (Same Seed)** — reload the full recipe unchanged
- **Variation (New Seed)** — same settings with a random seed
- **Prompt + New Seed** — apply only the prompt with a new seed
- **Generate Here** — run generation directly in the Prompt Manager tab (with progress and cancel)
- **Use All Settings in Generator** — loads the full generation recipe, including start/end frames when supported by the model

### Saved library

- **Save to Library** with tags for prompts you want to keep
- **Saved Library** view mode to browse saved prompts independently of disk files
- **Export Library** — download your library as JSON
- **Import Library JSON** — merge entries from a backup (skips duplicates)

### Bulk actions

Ctrl/Cmd+click to multi-select items, then:

- **Delete Selected**
- **Save Selected to Library**
- **Export Selected Prompts** — download prompts as a text file

### Other

- Hover **×** on thumbnails to delete files (or remove library entries)
- Collapsible long prompts in the metadata panel
- Standalone plugin — no other Wan2GP plugins required

## Requirements

- [Wan2GP](https://github.com/deepbeepmeep/Wan2GP) (WanGP / WangP)
- No extra Python dependencies

## Installation

### From the Wan2GP UI (recommended)

1. Open Wan2GP and go to the **Plugins** tab.
2. Under **Install New Plugin**, paste this repository URL:

   ```
   https://github.com/davidbrum25/wan2gp-prompt-manager
   ```

3. Click **Download and Install Plugin**.
4. Enable **Prompt Manager** in the plugin list.
5. **Restart Wan2GP**.

### Manual installation

1. Clone this repository into your Wan2GP `plugins/` folder:

   ```bash
   cd /path/to/Wan2GP/plugins
   git clone https://github.com/davidbrum25/wan2gp-prompt-manager.git
   ```

2. Enable `wan2gp-prompt-manager` in **Plugins** → save settings → restart Wan2GP.

## Usage

1. Open the **Prompt Manager** tab.
2. Click **Refresh Files** to scan your output folders.
3. Select an image or video from the grid.
4. Click any metadata row (e.g. **Prompt ▸**) to send only that value to the Media Generator, use **📋** to copy a value, or click **Use All Settings in Generator** for the full recipe.
5. Use **Generate Here** to run a generation without leaving the tab, or switch to **Saved Library** to browse your tagged prompt collection.

**Multi-select:** Hold Ctrl (Cmd on Mac) and click multiple thumbnails for bulk delete, save, or export.

Files without embedded WanGP metadata still show a preview and basic file info, but clickable fields, variations, and **Use All Settings** are only available when generation metadata is present.

## Updating

If you installed via the Plugins UI from GitHub, use **Update** on the plugin in the Plugins tab, then restart Wan2GP.

## Changelog

### v1.4.0

```
feat: add sidebar collapse toggle, interactive fullscreen view (zoom/pan/arrows), custom folder integration with native dialogue and combined view
```

- Added sidebar collapse/expand toggle button (`◀` / `▶`) with browser local storage state persistence.
- Added advanced interactive fullscreen view for images and videos:
  - Double-click a thumbnail in the grid or the preview box to enter fullscreen.
  - Keyboard arrow keys (Left/Right, Up/Down) to navigate through items in fullscreen.
  - Mouse scroll wheel to zoom in/out (up to 10x) and mouse drag to pan when zoomed.
  - Native browser fullscreen API integration.
- Added custom folder browser integration:
  - Added a `➕` button in the toolbar to register custom folder paths.
  - Launches a system-native file browser dialog using `zenity` (falling back to Tkinter if needed).
  - Custom folders are listed inside the `View` dropdown menu.
  - Added an `"All Folders"` option to aggregate and view files from all default outputs and custom folders combined.
  - Added a `➖` button to remove custom folders, prompting with confirmation or selection dialog.

### v1.3.1

```
feat: update plugin logic, add settings, and initialize git repositories for gallery, lora, and prompt managers
```

- Reorganized UI into a three-column layout (sidebar, grid, metadata panel)
- Added icon toolbar for refresh, open folder, export library, and import library
- Added grid zoom slider with browser-local persistence
- Improved metadata panel with collapsible long prompts

## Author

**David Brum**  
[davidbrum.5@gmail.com](mailto:davidbrum.5@gmail.com)

## License

MIT — see [LICENSE](LICENSE).