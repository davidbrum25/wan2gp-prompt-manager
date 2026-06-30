import html
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

import gradio as gr
from PIL import Image

from shared.utils.plugins import WAN2GPPlugin

from .library_store import (
    export_library_json,
    find_by_id,
    find_by_source_path,
    import_library_entries,
    library_entry_to_grid_entry,
    load_library,
    remove_by_id,
    upsert_entry,
)
from .media_utils import get_thumbnails_in_batch

VIEW_OUTPUTS = "Outputs"
VIEW_LIBRARY = "Saved Library"
LIBRARY_PATH_PREFIX = "lib://"

FIELD_LABELS = {
    "model": "Model",
    "prompt": "Prompt",
    "seed": "Seed",
    "resolution": "Resolution",
    "steps": "Steps",
    "cfg": "CFG",
    "loras": "LoRAs",
}

FILTER_MODEL_ALL = "All models"
FILTER_MEDIA_ALL = "All media"
FILTER_MEDIA_IMAGE = "Images only"
FILTER_MEDIA_VIDEO = "Videos only"
FILTER_PERIOD_ALL = "All time"
FILTER_PERIOD_TODAY = "Today"
FILTER_PERIOD_7D = "Last 7 days"
FILTER_PERIOD_30D = "Last 30 days"
FILTER_PERIOD_90D = "Last 90 days"

SORT_NEWEST = "Newest first"
SORT_OLDEST = "Oldest first"
SORT_MODEL_AZ = "Model A→Z"
SORT_PROMPT_LEN = "Prompt length"

GRID_SIZE_COMPACT = "Compact"
GRID_SIZE_COMFORTABLE = "Comfortable"
GRID_SIZE_LARGE = "Large"

METADATA_EXTENSIONS = (".txt", ".json", ".metadata")


class PromptManagerPlugin(WAN2GPPlugin):
    def __init__(self):
        super().__init__()
        self.loaded_once = False
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))

    def setup_ui(self):
        self.add_tab(
            tab_id="prompt_manager_tab",
            label="Prompt Manager",
            component_constructor=self.create_prompt_manager_ui,
            position=1,
        )
        self.request_global("server_config")
        self.request_global("has_video_file_extension")
        self.request_global("has_image_file_extension")
        self.request_global("get_settings_from_file")
        self.request_global("get_video_info")
        self.request_global("get_video_frame")
        self.request_global("get_file_creation_date")
        self.request_global("are_model_types_compatible")
        self.request_global("get_model_def")
        self.request_global("get_default_settings")
        self.request_global("get_model_settings")
        self.request_global("get_state_model_type")
        self.request_global("set_model_settings")
        self.request_global("add_to_sequence")
        self.request_global("generate_dropdown_model_list")
        self.request_global("get_unique_id")
        self.request_component("state")
        self.request_component("main_tabs")
        self.request_component("model_family")
        self.request_component("model_choice")
        self.request_component("refresh_form_trigger")

    def create_prompt_manager_ui(self, api_session):
        css = """
            #pm-layout {
                display: flex;
                gap: 12px;
                min-height: 78vh;
                align-items: stretch;
                width: 100%;
            }
            #pm-sidebar {
                flex: 0 0 240px;
                max-width: 260px;
                min-width: 220px;
                display: flex !important;
                flex-direction: column !important;
                flex-wrap: nowrap !important;
                gap: 10px;
                max-height: 84vh;
                overflow-y: auto !important;
                overflow-x: hidden !important;
                border: 1px solid var(--border-color-primary);
                padding: 12px;
                background-color: var(--background-fill-primary);
                border-radius: 8px;
            }
            #pm-sidebar .pm-sidebar-section {
                display: flex !important;
                flex-direction: column !important;
                gap: 8px;
            }
            #pm-sidebar .pm-sidebar-section + .pm-sidebar-section {
                padding-top: 10px;
                border-top: 1px solid var(--border-color-primary);
            }
            #pm-sidebar .pm-section-label {
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--body-text-color-subdued);
                margin: 0 0 2px 0;
            }
            #pm-sidebar .pm-section-label:not(:first-child) {
                padding-top: 10px;
                border-top: 1px solid var(--border-color-primary);
                margin-top: 4px;
            }
            #pm-sidebar .pm-section-label p {
                margin: 0;
            }
            #pm-sidebar .pm-sidebar-btn {
                width: 100%;
                flex-shrink: 0 !important;
            }
            #pm-browse-header {
                display: flex !important;
                flex-direction: row !important;
                flex-wrap: nowrap !important;
                align-items: center !important;
                justify-content: flex-end !important;
                gap: 8px !important;
                width: 100% !important;
            }
            #pm-browse-header .pm-section-label {
                flex-grow: 1 !important;
                margin: 0 !important;
            }
            #pm-sidebar .pm-icon-btn {
                width: 32px !important;
                min-width: 32px !important;
                max-width: 32px !important;
                height: 32px !important;
                padding: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                font-size: 16px !important;
                margin: 0 !important;
                flex-shrink: 0 !important;
                border-radius: 6px !important;
                background-color: var(--background-fill-secondary) !important;
                border: 1px solid var(--border-color-primary) !important;
                color: var(--body-text-color) !important;
                cursor: pointer !important;
                transition: all 0.15s ease !important;
            }
            #pm-sidebar .pm-icon-btn:hover {
                background-color: var(--background-fill-primary) !important;
                border-color: var(--border-color-accent) !important;
                color: var(--primary-500) !important;
            }
            #pm-import-upload {
                display: none !important;
            }
            #pm-sidebar .block {
                width: 100% !important;
                min-width: 100% !important;
                max-width: 100% !important;
                margin: 0 !important;
                flex-shrink: 0 !important;
            }
            #pm-sidebar .form,
            #pm-sidebar .gr-form {
                display: flex !important;
                flex-direction: column !important;
                flex-wrap: nowrap !important;
                width: 100% !important;
                min-width: 0 !important;
            }
            #pm-sidebar > *,
            #pm-sidebar .form > *,
            #pm-sidebar .gr-form > * {
                flex-shrink: 0 !important;
            }
            #pm-grid-container {
                flex: 1;
                min-width: 0;
                max-height: 82vh;
                overflow-y: auto;
                border: 1px solid var(--border-color-primary);
                padding: 10px;
                background-color: var(--background-fill-secondary);
                border-radius: 8px;
            }
            #pm-detail-panel {
                flex: 0 0 320px;
                max-width: 380px;
                min-width: 280px;
                max-height: 82vh;
                overflow-y: auto !important;
                overflow-x: hidden !important;
                border: 1px solid var(--border-color-primary);
                padding: 12px;
                background-color: var(--background-fill-primary);
                border-radius: 8px;
                display: flex !important;
                flex-direction: column !important;
                flex-wrap: nowrap !important;
                gap: 8px;
            }
            #pm-detail-panel .block {
                width: 100% !important;
                min-width: 100% !important;
                max-width: 100% !important;
                margin: 0 !important;
                flex-shrink: 0 !important;
                overflow: hidden !important;
            }
            #pm-detail-panel .form,
            #pm-detail-panel .gr-form {
                display: flex !important;
                flex-direction: column !important;
                flex-wrap: nowrap !important;
                width: 100% !important;
                min-width: 0 !important;
                gap: 8px !important;
            }
            #pm-detail-panel > *,
            #pm-detail-panel .form > *,
            #pm-detail-panel .gr-form > * {
                flex-shrink: 0 !important;
            }
            /* Ensure Gradio Image/Video preview wrappers don't overflow the detail panel */
            #pm-detail-panel .image-container,
            #pm-detail-panel .video-container,
            #pm-detail-panel .wrap,
            #pm-detail-panel .svelte-1adwusx,
            #pm-detail-panel .svelte-jox3wf,
            #pm-detail-panel .svelte-11xb1hd {
                width: 100% !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
            }
            #pm-detail-panel img,
            #pm-detail-panel video {
                max-width: 100% !important;
                object-fit: contain !important;
            }
            #pm-detail-panel :fullscreen img,
            #pm-detail-panel :fullscreen video,
            #pm-detail-panel :-webkit-full-screen img,
            #pm-detail-panel :-webkit-full-screen video,
            #pm-detail-panel :-moz-full-screen img,
            #pm-detail-panel :-moz-full-screen video {
                max-height: 100% !important;
                max-width: 100% !important;
                width: auto !important;
                height: auto !important;
                object-fit: contain !important;
            }
            #pm-detail-panel .source-selection,
            #pm-detail-panel [data-testid="source-select"] {
                display: none !important;
            }
            #pm-detail-panel .icon-buttons,
            #pm-detail-panel .image-buttons,
            #pm-detail-panel .download-button-wrapper {
                right: 8px !important;
                top: 8px !important;
                transform: scale(0.8) !important;
                transform-origin: top right !important;
                gap: 4px !important;
            }
            #pm-detail-panel button {
                width: 100%;
                flex-shrink: 0 !important;
            }
            #pm-detail-panel .image-container button,
            #pm-detail-panel .video-container button,
            #pm-detail-panel .pm-copy-btn {
                width: auto !important;
            }
            #pm-detail-panel .pm-detail-actions {
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .pm-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(var(--grid-item-size, 120px), 1fr));
                gap: 16px;
            }
            .pm-grid.pm-grid-compact {
                grid-template-columns: repeat(auto-fill, minmax(var(--grid-item-size, 88px), 1fr));
                gap: 10px;
            }
            .pm-grid.pm-grid-large {
                grid-template-columns: repeat(auto-fill, minmax(var(--grid-item-size, 168px), 1fr));
                gap: 20px;
            }
            #pm-grid-column {
                display: flex !important;
                flex-direction: column !important;
                flex: 1 !important;
                min-width: 0 !important;
            }
            #pm-grid-toolbar {
                display: flex !important;
                flex-direction: row !important;
                flex-wrap: nowrap !important;
                align-items: center !important;
                justify-content: space-between !important;
                width: 100% !important;
                margin-bottom: 8px !important;
                background-color: var(--background-fill-secondary);
                padding: 6px 12px !important;
                border-radius: 8px;
                border: 1px solid var(--border-color-primary);
                flex-shrink: 0 !important;
            }
            .pm-toolbar-title {
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                color: var(--body-text-color-subdued);
                letter-spacing: 0.04em;
                margin: 0 !important;
            }
            #pm-zoom-container {
                display: flex !important;
                flex-direction: row !important;
                flex-wrap: nowrap !important;
                align-items: center !important;
                gap: 6px !important;
                margin: 0 !important;
                width: auto !important;
                flex-shrink: 0 !important;
                flex: 0 0 auto !important;
            }
            #pm-zoom-container > * {
                flex: 0 0 auto !important;
                width: auto !important;
            }
            .pm-zoom-icon {
                font-size: 11px;
                color: var(--body-text-color-subdued);
                user-select: none;
            }
            #pm-grid-zoom {
                width: 240px !important;
                min-width: 240px !important;
                background: transparent !important;
                border: none !important;
                padding: 0 !important;
                margin: 0 !important;
                box-shadow: none !important;
                flex-shrink: 0 !important;
            }
            #pm-grid-zoom .wrap {
                padding: 0 !important;
                display: flex !important;
                flex-direction: row-reverse !important;
                align-items: center !important;
                gap: 8px !important;
                width: 100% !important;
                overflow: visible !important;
            }
            #pm-grid-zoom .head {
                display: flex !important;
                flex-direction: row !important;
                align-items: center !important;
                gap: 4px !important;
                margin-bottom: 0 !important;
                width: auto !important;
                flex-shrink: 0 !important;
                background: transparent !important;
                border: none !important;
                padding: 0 !important;
            }
            #pm-grid-zoom .head label {
                display: none !important;
            }
            #pm-grid-zoom .head input[type="number"] {
                width: 48px !important;
                min-width: 48px !important;
                height: 22px !important;
                padding: 0 2px !important;
                font-size: 11px !important;
                text-align: center !important;
                border-radius: 4px !important;
                border: 1px solid var(--border-color-primary) !important;
                background-color: var(--background-fill-primary) !important;
                color: var(--body-text-color) !important;
            }
            #pm-grid-zoom .head button,
            #pm-grid-zoom button.reset-button {
                background: transparent !important;
                border: none !important;
                padding: 0 !important;
                margin: 0 !important;
                cursor: pointer !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                width: 16px !important;
                height: 16px !important;
                min-width: 16px !important;
                align-self: center !important;
            }
            #pm-grid-zoom button.reset-button svg,
            #pm-grid-zoom .head button svg {
                align-self: center !important;
                margin: 0 !important;
            }
            #pm-grid-zoom .slider_input_container,
            #pm-grid-zoom .wrap > input[type="range"],
            #pm-grid-zoom .wrap > div:not(.head) {
                flex-grow: 1 !important;
                margin: 0 !important;
                width: auto !important;
                min-width: 0 !important;
                overflow: visible !important;
            }
            .pm-item {
                position: relative;
                cursor: pointer;
                border: 2px solid transparent;
                border-radius: 8px;
                overflow: hidden;
                aspect-ratio: 1 / 1;
                display: flex;
                flex-direction: column;
                background-color: var(--background-fill-primary);
                transition: all 0.2s ease-in-out;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            .pm-item:hover {
                border-color: var(--border-color-accent);
                transform: translateY(-2px);
            }
            .pm-item.selected {
                border-color: var(--primary-500);
                box-shadow: 0 0 0 3px var(--primary-200);
            }
            .pm-item-thumb {
                flex: 1;
                min-height: 0;
                background-color: var(--panel-background-fill);
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
            }
            .pm-item-thumb img, .pm-item-thumb video {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }
            .pm-item-label {
                padding: 4px 6px;
                font-size: 10px;
                text-align: center;
                background-color: var(--panel-background-fill);
                color: var(--body-text-color-subdued);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                border-top: 1px solid var(--border-color-primary);
            }
            .pm-delete-btn {
                position: absolute;
                top: 4px;
                right: 4px;
                width: 22px;
                height: 22px;
                border: none;
                border-radius: 50%;
                background: rgba(220, 38, 38, 0.92);
                color: #fff;
                font-size: 15px;
                font-weight: 700;
                line-height: 1;
                cursor: pointer;
                opacity: 0;
                transition: opacity 0.15s ease;
                z-index: 3;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0;
            }
            .pm-item:hover .pm-delete-btn {
                opacity: 1;
            }
            .pm-delete-btn:hover {
                background: #ff3333;
            }
            .pm-type-badge {
                position: absolute;
                left: 4px;
                bottom: 22px;
                font-size: 9px;
                padding: 1px 5px;
                border-radius: 4px;
                background: rgba(0, 0, 0, 0.55);
                color: #fff;
                z-index: 2;
                pointer-events: none;
            }
            .pm-fav-badge {
                position: absolute;
                top: 4px;
                left: 4px;
                font-size: 12px;
                z-index: 2;
                pointer-events: none;
                text-shadow: 0 1px 2px rgba(0,0,0,0.8);
            }
            .pm-item.pm-saved {
                border-color: rgba(234, 179, 8, 0.45);
            }
            .pm-metadata {
                font-family: monospace;
                font-size: 13px;
                line-height: 1.6;
                word-wrap: break-word;
            }
            .pm-metadata .placeholder {
                color: var(--body-text-color-subdued);
                text-align: center;
                margin-top: 20px;
                font-style: italic;
            }
            .pm-clickable {
                cursor: pointer;
                transition: background-color 0.15s ease;
            }
            .pm-clickable:hover {
                background-color: var(--background-fill-secondary);
            }
            .pm-clickable td:first-child {
                color: var(--primary-500);
                font-weight: 600;
                white-space: nowrap;
                vertical-align: top;
                width: 90px;
            }
            .pm-clickable td:last-child {
                font-weight: bold;
                word-wrap: break-word;
                word-break: break-word;
                white-space: pre-wrap;
            }
            .pm-prompt-wrapper {
                position: relative;
                display: block;
                width: 100%;
            }
            .pm-prompt-text {
                display: block;
                word-wrap: break-word;
                word-break: break-word;
                white-space: pre-wrap;
            }
            .pm-prompt-text.collapsed {
                display: -webkit-box !important;
                -webkit-line-clamp: 4;
                -webkit-box-orient: vertical;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .pm-prompt-toggle {
                display: inline-block;
                background: var(--background-fill-secondary);
                border: 1px solid var(--border-color-primary);
                color: var(--primary-500);
                cursor: pointer;
                font-size: 11px;
                font-weight: bold;
                padding: 1px 6px;
                margin-top: 4px;
                border-radius: 4px;
                line-height: 1.2;
                transition: all 0.15s ease;
            }
            .pm-prompt-toggle:hover {
                background: var(--background-fill-primary);
                color: var(--primary-400);
            }
            .pm-copy-btn {
                cursor: pointer;
                border: none;
                background: transparent;
                color: var(--body-text-color-subdued);
                font-size: 14px;
                padding: 2px 6px;
                border-radius: 4px;
                line-height: 1;
            }
            .pm-copy-btn:hover {
                color: var(--primary-500);
                background-color: var(--background-fill-secondary);
            }
            #pm-bulk-row {
                flex-direction: column !important;
                align-items: stretch !important;
                gap: 6px !important;
            }
            #pm-bulk-count {
                font-size: 12px;
                color: var(--body-text-color-subdued);
                text-align: center;
            }
            .pm-hint {
                font-size: 12px;
                color: var(--body-text-color-subdued);
                margin-bottom: 10px;
            }
            #pm_info {
                width: 100% !important;
                table-layout: fixed;
                border-collapse: collapse;
            }
            #pm_info TR, #pm_info TD {
                background-color: transparent;
                color: inherit;
                padding: 6px 4px;
                border: 1px dashed #6e789f4f !important;
                font-size: 12px;
            }
            #pm-filter-count {
                font-size: 12px;
                color: var(--body-text-color-subdued);
                text-align: center;
                padding: 4px 0;
            }
            #pm-sidebar .pm-header-text {
                margin: 0 0 10px 0 !important;
                border-bottom: 1px solid var(--border-color-primary);
                padding-bottom: 12px;
                flex-shrink: 0 !important;
            }
            #pm-sidebar .pm-header-text h3 {
                font-size: 15px !important;
                margin: 0 0 4px 0 !important;
                font-weight: 700 !important;
                color: var(--body-text-color) !important;
            }
            #pm-sidebar .pm-header-text p {
                font-size: 11px !important;
                line-height: 1.4 !important;
                color: var(--body-text-color-subdued) !important;
                margin: 0 !important;
            }
        """

        js = """
            function() {
                // Set tooltips for icon buttons
                setTimeout(() => {
                    const rBtn = document.getElementById('pm-refresh-btn');
                    if (rBtn) rBtn.setAttribute('title', 'Refresh Files');
                    const oBtn = document.getElementById('pm-open-outputs-btn');
                    if (oBtn) oBtn.setAttribute('title', 'Open Outputs Folder');
                    const eBtn = document.getElementById('pm-export-library-btn');
                    if (eBtn) eBtn.setAttribute('title', 'Export Library');
                    const iBtn = document.getElementById('pm-import-library-btn');
                    if (iBtn) iBtn.setAttribute('title', 'Import Library JSON');
                }, 300);

                // Restore zoom level
                setTimeout(() => {
                    const savedZoom = localStorage.getItem('pm-grid-zoom');
                    if (savedZoom) {
                        const container = document.getElementById('pm-grid-container');
                        if (container) {
                            container.style.setProperty('--grid-item-size', savedZoom + 'px');
                        }
                        const sliderInput = document.querySelector('#pm-grid-zoom input[type="range"]');
                        if (sliderInput) {
                            sliderInput.value = savedZoom;
                            sliderInput.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    }
                }, 400);

                window.togglePMPrompt = function(btn) {
                    const textEl = btn.previousElementSibling;
                    if (textEl.classList.contains('collapsed')) {
                        textEl.classList.remove('collapsed');
                        btn.textContent = 'Hide';
                    } else {
                        textEl.classList.add('collapsed');
                        btn.textContent = '...';
                    }
                };

                window.copyPromptManagerValue = function(button) {
                    const row = button.closest('tr');
                    if (!row) return;
                    const valueNode = row.querySelector('td b');
                    const text = valueNode ? valueNode.innerText : '';
                    if (!text) return;
                    const done = () => {
                        const original = button.textContent;
                        button.textContent = '✓';
                        setTimeout(() => { button.textContent = original; }, 1200);
                    };
                    if (navigator.clipboard && navigator.clipboard.writeText) {
                        navigator.clipboard.writeText(text).then(done).catch(() => {});
                    }
                };

                window.selectPromptManagerItem = function(event, element) {
                    if (element.classList.contains('pm-folder')) return;

                    const grid = element.closest('.pm-grid');
                    const selectedInput = document.querySelector('#pm-selected-file textarea');
                    const multiInput = document.querySelector('#pm-selected-files textarea');
                    if (!grid || !selectedInput) return;

                    if (!event.ctrlKey && !event.metaKey) {
                        grid.querySelectorAll('.pm-item.selected').forEach(el => {
                            if (el !== element) el.classList.remove('selected');
                        });
                    }
                    element.classList.toggle('selected');
                    const selected = Array.from(grid.querySelectorAll('.pm-item.selected:not(.pm-folder)'));
                    const paths = selected.map(el => el.dataset.path).filter(Boolean);
                    const path = paths.length === 1 ? paths[0] : '';
                    selectedInput.value = path;
                    selectedInput.dispatchEvent(new Event('input', { bubbles: true }));
                    if (multiInput) {
                        multiInput.value = JSON.stringify(paths);
                        multiInput.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                };

                window.openPromptManagerFolder = function(event, element) {
                    event.preventDefault();
                    event.stopPropagation();
                    const dirInput = document.querySelector('#pm-current-dir textarea');
                    const selectedInput = document.querySelector('#pm-selected-file textarea');
                    if (!dirInput) return;
                    dirInput.value = element.dataset.path || '';
                    dirInput.dispatchEvent(new Event('input', { bubbles: true }));
                    if (selectedInput) {
                        selectedInput.value = '';
                        selectedInput.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                };

                window.applyPromptManagerField = function(field) {
                    const fileInput = document.querySelector('#pm-selected-file textarea');
                    const actionInput = document.querySelector('#pm-field-action textarea');
                    if (!fileInput || !actionInput || !fileInput.value) return;
                    actionInput.value = field + '||' + fileInput.value;
                    actionInput.dispatchEvent(new Event('input', { bubbles: true }));
                };

                window.deletePromptManagerItem = function(event, button) {
                    event.preventDefault();
                    event.stopPropagation();
                    const item = button.closest('.pm-item');
                    if (!item || item.classList.contains('pm-folder')) return;
                    const path = item.dataset.path;
                    if (!path) return;
                    const isLibrary = path.startsWith('lib://');
                    const msg = isLibrary
                        ? 'Remove this saved prompt from the library?'
                        : 'Delete this file from disk?';
                    if (!confirm(msg)) return;
                    const deleteInput = document.querySelector('#pm-delete-action textarea');
                    if (!deleteInput) return;
                    deleteInput.value = path;
                    deleteInput.dispatchEvent(new Event('input', { bubbles: true }));
                };
            }
        """

        with gr.Blocks() as blocks:
            gr.HTML(value=f"<style>{css}</style>")
            blocks.load(fn=None, js=js)
            with gr.Column(elem_id="prompt_manager_tab_container"):
                with gr.Row(elem_id="pm-layout"):
                    with gr.Column(elem_id="pm-sidebar"):
                        gr.Markdown(
                            "### Prompt Manager\n"
                            "Browse outputs, filter your library, and click metadata to send values to the Media Generator.",
                            elem_classes="pm-header-text",
                        )
                        with gr.Row(elem_id="pm-browse-header"):
                            gr.Markdown("Browse", elem_classes="pm-section-label")
                            self.refresh_btn = gr.Button(
                                "🔄",
                                variant="secondary",
                                elem_classes="pm-icon-btn",
                                elem_id="pm-refresh-btn",
                            )
                            self.open_outputs_btn = gr.Button(
                                "📁",
                                variant="secondary",
                                elem_classes="pm-icon-btn",
                                elem_id="pm-open-outputs-btn",
                            )
                            self.export_library_btn = gr.Button(
                                "📤",
                                variant="secondary",
                                elem_classes="pm-icon-btn",
                                elem_id="pm-export-library-btn",
                            )
                            self.import_library_btn = gr.Button(
                                "📥",
                                variant="secondary",
                                elem_classes="pm-icon-btn",
                                elem_id="pm-import-library-btn",
                            )
                        self.view_mode = gr.Dropdown(
                            label="View",
                            choices=[VIEW_OUTPUTS, VIEW_LIBRARY],
                            value=VIEW_OUTPUTS,
                        )
                        self.filter_count = gr.Markdown("", elem_id="pm-filter-count")

                        gr.Markdown("Search & filters", elem_classes="pm-section-label")
                        self.filter_search = gr.Textbox(
                            label="Search",
                            placeholder="Prompt, model, filename, tags...",
                        )
                        self.filter_model = gr.Dropdown(
                            label="Model",
                            choices=[FILTER_MODEL_ALL],
                            value=FILTER_MODEL_ALL,
                        )
                        self.filter_media = gr.Dropdown(
                            label="Media type",
                            choices=[FILTER_MEDIA_ALL, FILTER_MEDIA_IMAGE, FILTER_MEDIA_VIDEO],
                            value=FILTER_MEDIA_ALL,
                        )
                        self.filter_period = gr.Dropdown(
                            label="Date",
                            choices=[
                                FILTER_PERIOD_ALL,
                                FILTER_PERIOD_TODAY,
                                FILTER_PERIOD_7D,
                                FILTER_PERIOD_30D,
                                FILTER_PERIOD_90D,
                            ],
                            value=FILTER_PERIOD_ALL,
                        )
                        self.filter_sort = gr.Dropdown(
                            label="Sort",
                            choices=[SORT_NEWEST, SORT_OLDEST, SORT_MODEL_AZ, SORT_PROMPT_LEN],
                            value=SORT_NEWEST,
                        )
                        self.filter_grid_size = gr.Dropdown(
                            label="Grid size",
                            choices=[GRID_SIZE_COMPACT, GRID_SIZE_COMFORTABLE, GRID_SIZE_LARGE],
                            value=GRID_SIZE_COMFORTABLE,
                        )

                        with gr.Column(elem_id="pm-bulk-row", visible=False) as self.bulk_row:
                            gr.Markdown("Bulk actions", elem_classes="pm-section-label")
                            self.bulk_count = gr.Markdown("", elem_id="pm-bulk-count")
                            self.bulk_delete_btn = gr.Button(
                                "Delete Selected",
                                size="sm",
                                variant="stop",
                                elem_classes="pm-sidebar-btn",
                            )
                            self.bulk_save_btn = gr.Button(
                                "Save Selected to Library",
                                size="sm",
                                elem_classes="pm-sidebar-btn",
                            )
                            self.bulk_export_btn = gr.Button(
                                "Export Selected Prompts",
                                size="sm",
                                elem_classes="pm-sidebar-btn",
                            )

                        self.library_import_upload = gr.File(
                            label="Import Library JSON",
                            file_types=[".json"],
                            elem_id="pm-import-upload",
                        )
                        self.library_export_file = gr.File(label="Library export", visible=False)

                    with gr.Column(elem_id="pm-grid-column", scale=2):
                        with gr.Row(elem_id="pm-grid-toolbar"):
                            gr.HTML("<div class='pm-toolbar-title'>Grid View</div>")
                            with gr.Row(elem_id="pm-zoom-container"):
                                gr.HTML("<span class='pm-zoom-icon'>➖</span>")
                                self.grid_zoom_slider = gr.Slider(
                                    minimum=60,
                                    maximum=240,
                                    value=120,
                                    step=5,
                                    label="Zoom",
                                    show_label=False,
                                    elem_id="pm-grid-zoom",
                                )
                                gr.HTML("<span class='pm-zoom-icon'>➕</span>")
                        self.grid_html = gr.HTML(
                            value="<div class='pm-grid'><p class='placeholder'>Click 'Refresh Files' to load your outputs.</p></div>",
                            elem_id="pm-grid-container",
                        )

                    with gr.Column(elem_id="pm-detail-panel"):
                        with gr.Column(visible=False) as self.preview_row:
                            self.video_preview = gr.Video(label="Preview", interactive=False, height=200, visible=False)
                            self.image_preview = gr.Image(label="Preview", interactive=False, height=200, visible=False)
                        self.metadata_html = gr.HTML(
                            value="<div class='pm-metadata'><p class='placeholder'>Select a file to view metadata.</p></div>"
                        )
                        with gr.Column(visible=False) as self.variation_row:
                            self.variation_same_btn = gr.Button("Recreate (Same Seed)", size="sm")
                            self.variation_new_btn = gr.Button("Variation (New Seed)", size="sm")
                            self.variation_prompt_btn = gr.Button("Prompt + New Seed", size="sm")
                        with gr.Column(visible=False) as self.library_row:
                            self.save_library_btn = gr.Button("★ Save to Library", size="sm")
                            self.remove_library_btn = gr.Button("Remove from Library", size="sm", visible=False)
                            self.library_tags = gr.Textbox(
                                label="Tags",
                                placeholder="portrait, fantasy",
                            )
                        with gr.Column(visible=False) as self.generate_row:
                            self.generate_btn = gr.Button("Generate Here", variant="primary", size="sm")
                            self.generate_cancel_btn = gr.Button("Cancel", size="sm", visible=False)
                        with gr.Column(visible=False) as self.generate_output_row:
                            self.generate_preview_image = gr.Image(label="Generated output", height=180, visible=False)
                            self.generate_preview_video = gr.Video(label="Generated output", height=180, visible=False)
                        self.use_all_btn = gr.Button(
                            "Use All Settings in Generator",
                            variant="primary",
                            interactive=False,
                            visible=False,
                        )

                self.selected_file = gr.Text(visible=False, elem_id="pm-selected-file")
                self.selected_files = gr.Text(visible=False, elem_id="pm-selected-files")
                self.current_dir = gr.Text(visible=False, elem_id="pm-current-dir")
                self.field_action = gr.Text(visible=False, elem_id="pm-field-action")
                self.delete_action = gr.Text(visible=False, elem_id="pm-delete-action")
                self.file_cache = gr.Text(visible=False, elem_id="pm-file-cache")

        grid_outputs = [
            self.grid_html,
            self.selected_file,
            self.selected_files,
            self.metadata_html,
            self.preview_row,
            self.video_preview,
            self.image_preview,
            self.use_all_btn,
            self.current_dir,
            self.file_cache,
            self.filter_model,
            self.filter_count,
            self.bulk_row,
            self.bulk_count,
        ]
        no_grid_updates = {comp: gr.update() for comp in grid_outputs}

        list_inputs = [
            self.state,
            self.current_dir,
            self.file_cache,
            self.filter_model,
            self.filter_media,
            self.filter_period,
            self.view_mode,
            self.filter_search,
            self.filter_sort,
            self.filter_grid_size,
        ]

        def on_tab_select(
            current_state,
            current_dir,
            cache,
            model_f,
            media_f,
            period_f,
            view_mode,
            search_q,
            sort_f,
            grid_size_f,
            evt: gr.SelectData,
        ):
            if evt.value == "Prompt Manager" and not self.loaded_once:
                self.loaded_once = True
                return self.list_media_files(
                    current_state,
                    current_dir,
                    cache,
                    model_f,
                    media_f,
                    period_f,
                    view_mode,
                    search_q,
                    sort_f,
                    grid_size_f,
                    rescan=True,
                )
            return no_grid_updates

        self.main_tabs.select(
            fn=on_tab_select,
            inputs=list_inputs,
            outputs=grid_outputs,
        )

        self.refresh_btn.click(
            fn=lambda *args: self.list_media_files(*args, rescan=True),
            inputs=list_inputs,
            outputs=grid_outputs,
        )

        self.current_dir.change(
            fn=lambda *args: self.list_media_files(*args, rescan=True),
            inputs=list_inputs,
            outputs=grid_outputs,
            show_progress="hidden",
        )

        filter_inputs = list_inputs

        for component in (
            self.filter_model,
            self.filter_media,
            self.filter_period,
            self.view_mode,
            self.filter_search,
            self.filter_sort,
            self.filter_grid_size,
        ):
            component.change(
                fn=lambda *args: self.list_media_files(*args, rescan=False),
                inputs=filter_inputs,
                outputs=grid_outputs,
                show_progress="hidden",
            )

        detail_outputs = [
            self.metadata_html,
            self.preview_row,
            self.video_preview,
            self.image_preview,
            self.variation_row,
            self.library_row,
            self.save_library_btn,
            self.remove_library_btn,
            self.library_tags,
            self.generate_row,
            self.generate_btn,
            self.generate_cancel_btn,
            self.generate_output_row,
            self.generate_preview_image,
            self.generate_preview_video,
            self.use_all_btn,
        ]

        self.selected_file.change(
            fn=self.update_detail_panel,
            inputs=[self.selected_file, self.state],
            outputs=detail_outputs,
            show_progress="hidden",
        )

        apply_outputs = [
            self.model_family,
            self.model_choice,
            self.main_tabs,
            self.refresh_form_trigger,
        ]

        self.field_action.change(
            fn=self.apply_field_action,
            inputs=[self.field_action, self.state],
            outputs=apply_outputs,
            show_progress="hidden",
        )

        self.use_all_btn.click(
            fn=self.apply_all_settings,
            inputs=[self.selected_file, self.state],
            outputs=apply_outputs,
            show_progress="hidden",
        )

        self.variation_same_btn.click(
            fn=lambda path, state: self.apply_variation(path, state, "same_seed"),
            inputs=[self.selected_file, self.state],
            outputs=apply_outputs,
            show_progress="hidden",
        )
        self.variation_new_btn.click(
            fn=lambda path, state: self.apply_variation(path, state, "new_seed"),
            inputs=[self.selected_file, self.state],
            outputs=apply_outputs,
            show_progress="hidden",
        )
        self.variation_prompt_btn.click(
            fn=lambda path, state: self.apply_variation(path, state, "prompt_new_seed"),
            inputs=[self.selected_file, self.state],
            outputs=apply_outputs,
            show_progress="hidden",
        )

        self.save_library_btn.click(
            fn=self.save_to_library,
            inputs=[self.selected_file, self.state, self.library_tags],
            outputs=detail_outputs,
            show_progress="hidden",
        )
        self.remove_library_btn.click(
            fn=self.remove_from_library,
            inputs=[self.selected_file, self.state],
            outputs=detail_outputs,
            show_progress="hidden",
        )

        self.delete_action.change(
            fn=lambda *args: self.delete_media_file(*args, rescan=True),
            inputs=list_inputs + [self.delete_action, self.selected_file],
            outputs=grid_outputs,
            show_progress="hidden",
        )

        self.open_outputs_btn.click(
            fn=self.open_outputs_folder,
            inputs=[self.current_dir],
            show_progress="hidden",
        )

        self.selected_files.change(
            fn=self.update_bulk_bar,
            inputs=[self.selected_files],
            outputs=[self.bulk_row, self.bulk_count],
            show_progress="hidden",
        )

        self.bulk_delete_btn.click(
            fn=self.bulk_delete_selected,
            inputs=list_inputs + [self.selected_files, self.selected_file],
            outputs=grid_outputs,
            show_progress="hidden",
        )
        self.bulk_save_btn.click(
            fn=self.bulk_save_to_library,
            inputs=list_inputs + [self.selected_files, self.library_tags],
            outputs=grid_outputs,
            show_progress="hidden",
        )
        self.bulk_export_btn.click(
            fn=self.bulk_export_prompts,
            inputs=[self.selected_files, self.state],
            outputs=[self.library_export_file],
            show_progress="hidden",
        )

        self.export_library_btn.click(
            fn=self.export_library_file,
            outputs=[self.library_export_file],
            show_progress="hidden",
        )
        self.import_library_btn.click(
            fn=None,
            js="""() => {
                const fileInput = document.querySelector('#pm-import-upload input[type="file"]');
                if (fileInput) {
                    fileInput.click();
                }
            }"""
        )
        self.library_import_upload.change(
            fn=self.import_library_file,
            inputs=[self.library_import_upload] + list_inputs,
            outputs=grid_outputs,
            show_progress="hidden",
        )
        self.grid_zoom_slider.change(
            fn=None,
            inputs=[self.grid_zoom_slider],
            js="""(val) => {
                const container = document.getElementById('pm-grid-container');
                if (container) {
                    container.style.setProperty('--grid-item-size', val + 'px');
                }
                localStorage.setItem('pm-grid-zoom', val);
            }"""
        )

        active_job = {"job": None}

        def generate_here(file_path, state, progress=gr.Progress(track_tqdm=False)):
            settings = self._prepare_generation_settings(file_path, state)
            if not settings:
                gr.Warning("No settings found for this item.")
                return (
                    gr.Column(visible=False),
                    gr.Button(visible=False),
                    gr.Column(visible=False),
                    gr.Image(value=None, visible=False),
                    gr.Video(value=None, visible=False),
                )

            class GenCallbacks:
                ratio = 0.0

                def on_status(self, status):
                    status = str(status or "").strip()
                    if status:
                        progress(self.ratio, desc=status)

                def on_progress(self, update):
                    self.ratio = max(0.0, min(1.0, float(getattr(update, "progress", 0)) / 100.0))
                    progress(self.ratio, desc=str(getattr(update, "status", "") or "Generating..."))

            job = api_session.submit_task(settings, callbacks=GenCallbacks())
            active_job["job"] = job
            try:
                result = job.result()
            finally:
                if active_job.get("job") is job:
                    active_job["job"] = None

            if result.cancelled:
                gr.Info("Generation cancelled.")
                return (
                    gr.Column(visible=True),
                    gr.Button(visible=False),
                    gr.Column(visible=False),
                    gr.Image(value=None, visible=False),
                    gr.Video(value=None, visible=False),
                )
            if not result.success or not result.generated_files:
                errors = list(result.errors or [])
                gr.Warning(str(errors[0] if errors else "Generation completed without output."))
                return (
                    gr.Column(visible=True),
                    gr.Button(visible=False),
                    gr.Column(visible=False),
                    gr.Image(value=None, visible=False),
                    gr.Video(value=None, visible=False),
                )

            output_path = result.generated_files[0]
            gr.Info(f"Generated '{os.path.basename(output_path)}'.")
            if self.has_video_file_extension(output_path):
                return (
                    gr.Column(visible=True),
                    gr.Button(visible=False),
                    gr.Column(visible=True),
                    gr.Image(value=None, visible=False),
                    gr.Video(value=output_path, visible=True),
                )
            if self.has_image_file_extension(output_path):
                return (
                    gr.Column(visible=True),
                    gr.Button(visible=False),
                    gr.Column(visible=True),
                    gr.Image(value=Image.open(output_path), visible=True),
                    gr.Video(value=None, visible=False),
                )
            return (
                gr.Column(visible=True),
                gr.Button(visible=False),
                gr.Column(visible=False),
                gr.Image(value=None, visible=False),
                gr.Video(value=None, visible=False),
            )

        def cancel_generation():
            job = active_job.get("job")
            if job is not None and not job.done:
                job.cancel()

        generate_outputs = [
            self.generate_row,
            self.generate_cancel_btn,
            self.generate_output_row,
            self.generate_preview_image,
            self.generate_preview_video,
        ]

        self.generate_btn.click(
            fn=generate_here,
            inputs=[self.selected_file, self.state],
            outputs=generate_outputs,
            show_progress="full",
        )
        self.generate_btn.click(
            fn=lambda: gr.Button(visible=True),
            outputs=[self.generate_cancel_btn],
            show_progress="hidden",
            queue=False,
        )
        self.generate_cancel_btn.click(fn=cancel_generation, queue=False)

        return blocks

    def _output_roots(self):
        save_path = os.path.abspath(self.server_config.get("save_path", "outputs"))
        image_save_path = os.path.abspath(self.server_config.get("image_save_path", "outputs"))
        roots = []
        for path in (save_path, image_save_path):
            if path and os.path.isdir(path) and path not in roots:
                roots.append(path)
        return roots

    def _resolve_outputs_folder_to_open(self, current_dir=""):
        roots = self._output_roots()
        cur = (current_dir or "").strip()
        if cur:
            cur_abs = os.path.abspath(cur)
            if os.path.isdir(cur_abs) and self._is_within_roots(cur_abs, roots):
                return cur_abs

        save_path = os.path.abspath(self.server_config.get("save_path", "outputs"))
        if os.path.isdir(save_path):
            return save_path

        for root in roots:
            if os.path.isdir(root):
                return root
        return None

    def _open_path_in_file_manager(self, path):
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)

    def open_outputs_folder(self, current_dir=""):
        folder = self._resolve_outputs_folder_to_open(current_dir)
        if not folder:
            gr.Warning("Outputs folder not found. Check your save path in Settings.")
            return

        try:
            os.makedirs(folder, exist_ok=True)
            self._open_path_in_file_manager(folder)
            gr.Info(f"Opened outputs folder: {folder}")
        except Exception as exc:
            gr.Warning(f"Could not open folder: {exc}")

    def _is_within_roots(self, path, roots):
        abs_path = os.path.abspath(path)
        for root in roots:
            try:
                if os.path.commonpath([abs_path, root]) == root:
                    return True
            except Exception:
                pass
        return False

    def _format_short_date(self, timestamp):
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

    def _is_library_path(self, path):
        return isinstance(path, str) and path.startswith(LIBRARY_PATH_PREFIX)

    def _parse_library_id(self, path):
        if not self._is_library_path(path):
            return ""
        return path[len(LIBRARY_PATH_PREFIX) :]

    def _build_search_text(self, basename, model_name, prompt, tags=None):
        parts = [basename, model_name, prompt or ""]
        if tags:
            parts.append(", ".join(tags) if isinstance(tags, list) else str(tags))
        return " ".join(part for part in parts if part).lower()

    def _get_library_entries(self):
        return load_library(self.plugin_dir)

    def _get_saved_source_paths(self):
        return {
            os.path.abspath(entry.get("source_path", ""))
            for entry in self._get_library_entries()
            if entry.get("source_path")
        }

    def _describe_file(self, state, file_path, saved_paths=None):
        configs, _, _ = self.get_settings_from_file(state, file_path, False, False, False)
        is_video = self.has_video_file_extension(file_path)
        is_image = self.has_image_file_extension(file_path)
        model_name = self._format_model_name(configs) if configs else "Unknown model"
        prompt = (configs.get("prompt") or "") if configs else ""
        created_ts = os.path.getctime(file_path)
        abs_path = os.path.abspath(file_path)
        saved_paths = saved_paths or self._get_saved_source_paths()
        library_entry = find_by_source_path(self._get_library_entries(), abs_path)
        return {
            "path": abs_path,
            "basename": os.path.basename(file_path),
            "model": model_name or "Unknown model",
            "prompt": prompt,
            "search_text": self._build_search_text(
                os.path.basename(file_path),
                model_name or "Unknown model",
                prompt,
                library_entry.get("tags") if library_entry else None,
            ),
            "created": created_ts,
            "created_label": self._format_short_date(created_ts),
            "is_video": is_video,
            "is_image": is_image,
            "has_metadata": bool(configs and "seed" in configs),
            "is_library": False,
            "library_id": library_entry.get("id") if library_entry else None,
            "is_saved": abs_path in saved_paths,
            "source_path": abs_path,
            "file_exists": True,
            "tags": library_entry.get("tags", []) if library_entry else [],
        }

    def _library_entries_as_grid(self):
        return [library_entry_to_grid_entry(entry) for entry in self._get_library_entries()]

    def _scan_media_entries(self, state, current_dir=""):
        roots = self._output_roots()
        cur = (current_dir or "").strip()
        cur_abs = os.path.abspath(cur) if cur else ""

        if cur_abs and (not os.path.isdir(cur_abs) or not self._is_within_roots(cur_abs, roots)):
            cur_abs = ""

        folder_items = []
        file_paths = []
        seen_files = set()
        seen_folders = set()

        def add_folder(folder_path, display):
            abs_path = os.path.abspath(folder_path)
            if abs_path in seen_folders:
                return
            seen_folders.add(abs_path)
            folder_items.append({"path": abs_path, "name": display})

        def add_file(file_path):
            abs_path = os.path.abspath(file_path)
            if abs_path in seen_files:
                return
            seen_files.add(abs_path)
            file_paths.append(abs_path)

        def scan_dir(dir_path):
            try:
                entries = os.listdir(dir_path)
            except Exception as exc:
                print(f"Could not list directory {dir_path}: {exc}")
                return

            for name in entries:
                full = os.path.join(dir_path, name)
                if os.path.isdir(full):
                    add_folder(full, name)

            for name in entries:
                full = os.path.join(dir_path, name)
                if os.path.isfile(full) and (
                    self.has_video_file_extension(name) or self.has_image_file_extension(name)
                ):
                    add_file(full)

        if not cur_abs:
            for root in roots:
                scan_dir(root)
        else:
            parent = os.path.abspath(os.path.join(cur_abs, os.pardir))
            if parent and parent != cur_abs and self._is_within_roots(parent, roots):
                add_folder(parent, "⬆️ ..")
            scan_dir(cur_abs)

        folder_items.sort(key=lambda item: item["name"].lower())
        file_paths.sort(key=os.path.getctime, reverse=True)
        saved_paths = self._get_saved_source_paths()
        file_entries = [self._describe_file(state, path, saved_paths) for path in file_paths]
        return folder_items, file_entries, cur_abs

    def _period_cutoff(self, period_label):
        now = datetime.now()
        if period_label == FILTER_PERIOD_TODAY:
            return datetime(now.year, now.month, now.day).timestamp()
        if period_label == FILTER_PERIOD_7D:
            return (now - timedelta(days=7)).timestamp()
        if period_label == FILTER_PERIOD_30D:
            return (now - timedelta(days=30)).timestamp()
        if period_label == FILTER_PERIOD_90D:
            return (now - timedelta(days=90)).timestamp()
        return None

    def _grid_size_class(self, grid_size):
        if grid_size == GRID_SIZE_COMPACT:
            return "pm-grid pm-grid-compact"
        if grid_size == GRID_SIZE_LARGE:
            return "pm-grid pm-grid-large"
        return "pm-grid"

    def _apply_sort(self, entries, sort_by):
        sorted_entries = list(entries)
        if sort_by == SORT_OLDEST:
            sorted_entries.sort(key=lambda entry: entry.get("created", 0))
        elif sort_by == SORT_MODEL_AZ:
            sorted_entries.sort(key=lambda entry: (entry.get("model") or "").lower())
        elif sort_by == SORT_PROMPT_LEN:
            sorted_entries.sort(key=lambda entry: len(entry.get("prompt") or ""), reverse=True)
        else:
            sorted_entries.sort(key=lambda entry: entry.get("created", 0), reverse=True)
        return sorted_entries

    def _apply_filters(self, entries, filter_model, filter_media, filter_period, search_query=""):
        filtered = list(entries)
        if filter_media == FILTER_MEDIA_IMAGE:
            filtered = [entry for entry in filtered if entry["is_image"]]
        elif filter_media == FILTER_MEDIA_VIDEO:
            filtered = [entry for entry in filtered if entry["is_video"]]

        cutoff = self._period_cutoff(filter_period)
        if cutoff is not None:
            filtered = [entry for entry in filtered if entry["created"] >= cutoff]

        if filter_model and filter_model != FILTER_MODEL_ALL:
            filtered = [entry for entry in filtered if entry["model"] == filter_model]

        search_query = (search_query or "").strip().lower()
        if search_query:
            tokens = search_query.split()
            filtered = [
                entry
                for entry in filtered
                if all(token in (entry.get("search_text") or "") for token in tokens)
            ]

        return filtered

    def _model_filter_choices(self, entries):
        models = sorted({entry["model"] for entry in entries if entry.get("model")})
        return [FILTER_MODEL_ALL, *models]

    def _render_grid_html(self, folder_items, file_entries, grid_size=GRID_SIZE_COMFORTABLE):
        grid_class = self._grid_size_class(grid_size)
        thumb_targets = []
        for entry in file_entries:
            preview_path = entry.get("source_path") if entry.get("is_library") else entry["path"]
            if preview_path and os.path.isfile(preview_path) and (entry["is_video"] or entry["is_image"]):
                thumb_targets.append(preview_path)
        thumbnails = get_thumbnails_in_batch(thumb_targets)

        items_html = ""
        for folder in folder_items:
            safe_path = json.dumps(folder["path"], ensure_ascii=False)
            items_html += f"""
            <div class="pm-item pm-folder" data-path={safe_path} ondblclick="openPromptManagerFolder(event, this)">
                <div class="pm-item-thumb" style="display:flex;align-items:center;justify-content:center;font-size:42px;">📁</div>
                <div class="pm-item-label" title="{html.escape(folder['name'])}">{html.escape(folder['name'])}</div>
            </div>
            """

        for entry in file_entries:
            file_path = entry["path"]
            basename = entry["basename"]
            is_video = entry["is_video"]
            preview_path = entry.get("source_path") if entry.get("is_library") else file_path
            base64_thumb = thumbnails.get(os.path.abspath(preview_path)) if preview_path else None
            can_preview = preview_path and os.path.isfile(preview_path)
            if base64_thumb:
                thumb_html = f'<img src="data:image/jpeg;base64,{base64_thumb}" alt="thumb">'
            elif can_preview and is_video:
                thumb_html = f'<video muted preload="metadata" src="/gradio_api/file={preview_path}#t=0.5"></video>'
            elif can_preview:
                thumb_html = f'<img src="/gradio_api/file={preview_path}" alt="thumb">'
            else:
                thumb_html = (
                    '<div style="display:flex;align-items:center;justify-content:center;'
                    'height:100%;font-size:34px;opacity:0.55;">★</div>'
                )

            media_badge = "VIDEO" if is_video else "IMAGE"
            if entry.get("is_library") and not entry.get("file_exists"):
                media_badge = "SAVED"
            label = entry["created_label"]
            safe_path = json.dumps(file_path, ensure_ascii=False)
            saved_class = " pm-saved" if entry.get("is_saved") or entry.get("is_library") else ""
            fav_badge = '<span class="pm-fav-badge">★</span>' if entry.get("is_saved") or entry.get("is_library") else ""
            delete_title = "Remove from library" if entry.get("is_library") else "Delete file"
            items_html += f"""
            <div class="pm-item{saved_class}" data-path={safe_path} onclick="selectPromptManagerItem(event, this)">
                <button class="pm-delete-btn" onclick="deletePromptManagerItem(event, this)" title="{html.escape(delete_title)}">×</button>
                {fav_badge}
                <span class="pm-type-badge">{media_badge}</span>
                <div class="pm-item-thumb">{thumb_html}</div>
                <div class="pm-item-label" title="{html.escape(basename)}">{html.escape(label)}</div>
            </div>
            """

        if not items_html:
            return f"<div class='{grid_class}'><p class='placeholder'>No files match the current filters.</p></div>"
        return f"<div class='{grid_class}'>{items_html}</div>"

    def _empty_grid_response(self, cur_abs="", cache_json="[]"):
        clear_metadata = (
            "<div class='pm-metadata'><p class='placeholder'>Select a file to view metadata.</p></div>"
        )
        return {
            self.grid_html: "<div class='pm-grid'><p class='placeholder'>No images or videos found in output folders.</p></div>",
            self.selected_file: "",
            self.selected_files: "[]",
            self.metadata_html: clear_metadata,
            self.preview_row: gr.Column(visible=False),
            self.video_preview: gr.Video(value=None, visible=False),
            self.image_preview: gr.Image(value=None, visible=False),
            self.use_all_btn: gr.Button(visible=False, interactive=False),
            self.current_dir: cur_abs if cur_abs else "",
            self.file_cache: cache_json,
            self.filter_model: gr.Dropdown(choices=[FILTER_MODEL_ALL], value=FILTER_MODEL_ALL),
            self.filter_count: "",
            self.bulk_row: gr.Column(visible=False),
            self.bulk_count: "",
        }

    def list_media_files(
        self,
        current_state,
        current_dir="",
        file_cache="",
        filter_model=FILTER_MODEL_ALL,
        filter_media=FILTER_MEDIA_ALL,
        filter_period=FILTER_PERIOD_ALL,
        view_mode=VIEW_OUTPUTS,
        search_query="",
        sort_by=SORT_NEWEST,
        grid_size=GRID_SIZE_COMFORTABLE,
        rescan=True,
    ):
        if view_mode == VIEW_LIBRARY:
            file_entries = self._library_entries_as_grid()
            filtered_entries = self._apply_filters(
                file_entries, filter_model, filter_media, filter_period, search_query
            )
            filtered_entries = self._apply_sort(filtered_entries, sort_by)
            grid_html = self._render_grid_html([], filtered_entries, grid_size)
            total = len(file_entries)
            shown = len(filtered_entries)
            clear_metadata = (
                "<div class='pm-metadata'><p class='placeholder'>Select a saved prompt to view details.</p></div>"
            )
            model_choices = self._model_filter_choices(file_entries)
            if filter_model not in model_choices:
                filter_model = FILTER_MODEL_ALL
            return {
                self.grid_html: grid_html,
                self.selected_file: "",
                self.selected_files: "[]",
                self.metadata_html: clear_metadata,
                self.preview_row: gr.Column(visible=False),
                self.video_preview: gr.Video(value=None, visible=False),
                self.image_preview: gr.Image(value=None, visible=False),
                self.use_all_btn: gr.Button(visible=False, interactive=False),
                self.current_dir: "",
                self.file_cache: "",
                self.filter_model: gr.Dropdown(choices=model_choices, value=filter_model),
                self.filter_count: f"Showing **{shown}** of **{total}** saved prompts",
                self.bulk_row: gr.Column(visible=False),
                self.bulk_count: "",
            }

        folder_items = []
        file_entries = []
        cur_abs = ""

        if rescan or not (file_cache or "").strip():
            folder_items, file_entries, cur_abs = self._scan_media_entries(current_state, current_dir)
            cache_json = json.dumps(
                {"folders": folder_items, "files": file_entries, "dir": cur_abs},
                ensure_ascii=False,
            )
        else:
            folder_items = []
            file_entries = []
            cur_abs = ""
            try:
                cache_data = json.loads(file_cache)
                if isinstance(cache_data, dict):
                    folder_items = cache_data.get("folders", [])
                    file_entries = cache_data.get("files", [])
                    cur_abs = cache_data.get("dir", "") or ""
                elif isinstance(cache_data, list):
                    file_entries = cache_data
            except Exception:
                file_entries = []
            if not cur_abs:
                cur = (current_dir or "").strip()
                cur_abs = os.path.abspath(cur) if cur else ""
            cache_json = file_cache

        if not file_entries and not folder_items:
            return self._empty_grid_response(cur_abs, "[]")

        model_choices = self._model_filter_choices(file_entries)
        if filter_model not in model_choices:
            filter_model = FILTER_MODEL_ALL

        filtered_entries = self._apply_filters(
            file_entries, filter_model, filter_media, filter_period, search_query
        )
        filtered_entries = self._apply_sort(filtered_entries, sort_by)
        grid_html = self._render_grid_html(folder_items, filtered_entries, grid_size)
        clear_metadata = (
            "<div class='pm-metadata'><p class='placeholder'>Select a file to view metadata.</p></div>"
        )
        total = len(file_entries)
        shown = len(filtered_entries)
        count_text = f"Showing **{shown}** of **{total}** files"

        return {
            self.grid_html: grid_html,
            self.selected_file: "",
            self.selected_files: "[]",
            self.metadata_html: clear_metadata,
            self.preview_row: gr.Column(visible=False),
            self.video_preview: gr.Video(value=None, visible=False),
            self.image_preview: gr.Image(value=None, visible=False),
            self.use_all_btn: gr.Button(visible=False, interactive=False),
            self.current_dir: cur_abs if cur_abs else "",
            self.file_cache: cache_json,
            self.filter_model: gr.Dropdown(choices=model_choices, value=filter_model),
            self.filter_count: count_text,
            self.bulk_row: gr.Column(visible=False),
            self.bulk_count: "",
        }

    def _delete_file_from_disk(self, file_path):
        if not file_path or not os.path.exists(file_path):
            return False

        try:
            os.remove(file_path)
        except Exception as exc:
            gr.Warning(f"Could not delete file: {exc}")
            return False

        base_path = os.path.splitext(file_path)[0]
        for ext in METADATA_EXTENSIONS:
            metadata_path = base_path + ext
            if os.path.exists(metadata_path):
                try:
                    os.remove(metadata_path)
                except Exception as exc:
                    print(f"Could not delete metadata file {metadata_path}: {exc}")
        return True

    def delete_media_file(
        self,
        current_state,
        current_dir,
        file_cache,
        filter_model,
        filter_media,
        filter_period,
        view_mode,
        search_query,
        sort_by,
        grid_size,
        delete_path,
        selected_file,
        rescan=True,
    ):
        delete_path = (delete_path or "").strip()
        if not delete_path:
            return self.list_media_files(
                current_state,
                current_dir,
                file_cache,
                filter_model,
                filter_media,
                filter_period,
                view_mode,
                search_query,
                sort_by,
                grid_size,
                rescan=False,
            )

        if self._is_library_path(delete_path):
            entry_id = self._parse_library_id(delete_path)
            if remove_by_id(self.plugin_dir, entry_id):
                gr.Info("Removed from library.")
            else:
                gr.Warning("Could not remove saved prompt.")
            return self.list_media_files(
                current_state,
                current_dir,
                file_cache,
                filter_model,
                filter_media,
                filter_period,
                VIEW_LIBRARY,
                search_query,
                sort_by,
                grid_size,
                rescan=True,
            )

        if self._delete_file_from_disk(delete_path):
            gr.Info(f"Deleted '{os.path.basename(delete_path)}'.")
            if selected_file == delete_path:
                selected_file = ""
        else:
            gr.Warning(f"Failed to delete '{os.path.basename(delete_path)}'.")

        return self.list_media_files(
            current_state,
            current_dir,
            file_cache,
            filter_model,
            filter_media,
            filter_period,
            view_mode,
            search_query,
            sort_by,
            grid_size,
            rescan=True,
        )

    def _parse_selected_paths(self, selected_files_json):
        try:
            paths = json.loads(selected_files_json or "[]")
        except Exception:
            return []
        if not isinstance(paths, list):
            return []
        return [path for path in paths if isinstance(path, str) and path.strip()]

    def update_bulk_bar(self, selected_files_json):
        count = len(self._parse_selected_paths(selected_files_json))
        if count < 2:
            return gr.Column(visible=False), ""
        return gr.Column(visible=True), f"**{count}** items selected"

    def bulk_delete_selected(
        self,
        current_state,
        current_dir,
        file_cache,
        filter_model,
        filter_media,
        filter_period,
        view_mode,
        search_query,
        sort_by,
        grid_size,
        selected_files_json,
        selected_file,
    ):
        paths = self._parse_selected_paths(selected_files_json)
        if len(paths) < 2:
            gr.Warning("Select at least two items for bulk delete.")
            return self.list_media_files(
                current_state,
                current_dir,
                file_cache,
                filter_model,
                filter_media,
                filter_period,
                view_mode,
                search_query,
                sort_by,
                grid_size,
                rescan=False,
            )

        deleted = 0
        for path in paths:
            if self._is_library_path(path):
                if remove_by_id(self.plugin_dir, self._parse_library_id(path)):
                    deleted += 1
            elif self._delete_file_from_disk(path):
                deleted += 1

        gr.Info(f"Deleted {deleted} of {len(paths)} selected items.")
        return self.list_media_files(
            current_state,
            current_dir,
            file_cache,
            filter_model,
            filter_media,
            filter_period,
            view_mode,
            search_query,
            sort_by,
            grid_size,
            rescan=True,
        )

    def bulk_save_to_library(
        self,
        current_state,
        current_dir,
        file_cache,
        filter_model,
        filter_media,
        filter_period,
        view_mode,
        search_query,
        sort_by,
        grid_size,
        selected_files_json,
        tags_text,
    ):
        paths = self._parse_selected_paths(selected_files_json)
        if len(paths) < 2:
            gr.Warning("Select at least two items to save.")
            return self.list_media_files(
                current_state,
                current_dir,
                file_cache,
                filter_model,
                filter_media,
                filter_period,
                view_mode,
                search_query,
                sort_by,
                grid_size,
                rescan=False,
            )

        saved = 0
        for path in paths:
            if self._is_library_path(path):
                continue
            entry_data = self._library_entry_from_file(current_state, path, tags_text)
            if entry_data:
                upsert_entry(self.plugin_dir, entry_data)
                saved += 1

        gr.Info(f"Saved {saved} of {len(paths)} items to library.")
        return self.list_media_files(
            current_state,
            current_dir,
            file_cache,
            filter_model,
            filter_media,
            filter_period,
            view_mode,
            search_query,
            sort_by,
            grid_size,
            rescan=True,
        )

    def bulk_export_prompts(self, selected_files_json, state):
        paths = self._parse_selected_paths(selected_files_json)
        if len(paths) < 2:
            gr.Warning("Select at least two items to export prompts.")
            return gr.File(visible=False)

        lines = []
        for path in paths:
            configs = self._load_configs(state, path)
            prompt = (configs or {}).get("prompt") or ""
            label = os.path.basename(self._resolve_preview_path(path) or path)
            if self._is_library_path(path):
                entry = self._get_library_entry(path)
                label = entry.get("basename", "saved prompt") if entry else "saved prompt"
            lines.append(f"--- {label} ---\n{prompt}\n")

        export_path = os.path.join(tempfile.gettempdir(), f"prompt_manager_export_{datetime.now():%Y%m%d_%H%M%S}.txt")
        with open(export_path, "w", encoding="utf-8") as writer:
            writer.write("\n".join(lines))
        gr.Info(f"Exported {len(paths)} prompts.")
        return gr.File(value=export_path, visible=True)

    def export_library_file(self):
        export_path = os.path.join(tempfile.gettempdir(), f"prompts_library_{datetime.now():%Y%m%d_%H%M%S}.json")
        with open(export_path, "w", encoding="utf-8") as writer:
            writer.write(export_library_json(self.plugin_dir))
        gr.Info("Library exported.")
        return gr.File(value=export_path, visible=True)

    def import_library_file(
        self,
        upload_file,
        current_state,
        current_dir,
        file_cache,
        filter_model,
        filter_media,
        filter_period,
        view_mode,
        search_query,
        sort_by,
        grid_size,
    ):
        if upload_file is None:
            return self.list_media_files(
                current_state,
                current_dir,
                file_cache,
                filter_model,
                filter_media,
                filter_period,
                view_mode,
                search_query,
                sort_by,
                grid_size,
                rescan=False,
            )

        try:
            path = upload_file if isinstance(upload_file, str) else upload_file.name
            with open(path, "r", encoding="utf-8") as reader:
                payload = json.load(reader)
            added, skipped = import_library_entries(self.plugin_dir, payload, merge=True)
            gr.Info(f"Imported {added} entries ({skipped} skipped as duplicates).")
        except Exception as exc:
            gr.Warning(f"Could not import library: {exc}")
            return self.list_media_files(
                current_state,
                current_dir,
                file_cache,
                filter_model,
                filter_media,
                filter_period,
                view_mode,
                search_query,
                sort_by,
                grid_size,
                rescan=False,
            )

        return self.list_media_files(
            current_state,
            current_dir,
            file_cache,
            filter_model,
            filter_media,
            filter_period,
            VIEW_LIBRARY,
            search_query,
            sort_by,
            grid_size,
            rescan=True,
        )

    def _get_library_entry(self, file_path):
        if not self._is_library_path(file_path):
            return None
        return find_by_id(self._get_library_entries(), self._parse_library_id(file_path))

    def _resolve_preview_path(self, file_path):
        if self._is_library_path(file_path):
            entry = self._get_library_entry(file_path)
            if entry:
                source_path = entry.get("source_path", "")
                if source_path and os.path.isfile(source_path):
                    return source_path
            return ""
        return file_path

    def _load_configs(self, state, file_path):
        if not file_path:
            return None
        if self._is_library_path(file_path):
            entry = self._get_library_entry(file_path)
            if not entry:
                return None
            return dict(entry.get("settings") or {})
        configs, _, _ = self.get_settings_from_file(state, file_path, True, True, True)
        return configs

    def _library_entry_from_file(self, state, file_path, tags_text=""):
        configs = self._load_configs(state, file_path)
        if not configs or "seed" not in configs:
            return None
        tags = [tag.strip() for tag in (tags_text or "").split(",") if tag.strip()]
        abs_path = os.path.abspath(file_path)
        created_ts = os.path.getctime(abs_path) if os.path.isfile(abs_path) else datetime.now().timestamp()
        model_name = self._format_model_name(configs) or "Unknown model"
        prompt = configs.get("prompt") or ""
        return {
            "source_path": abs_path,
            "basename": os.path.basename(abs_path),
            "prompt": prompt,
            "model": model_name,
            "model_type": configs.get("model_type", ""),
            "seed": configs.get("seed"),
            "resolution": configs.get("resolution", ""),
            "settings": configs,
            "tags": tags,
            "notes": "",
            "is_video": self.has_video_file_extension(abs_path),
            "is_image": self.has_image_file_extension(abs_path),
            "created": created_ts,
            "created_label": self._format_short_date(created_ts),
            "search_text": self._build_search_text(os.path.basename(abs_path), model_name, prompt, tags),
        }

    def _format_model_name(self, configs):
        if not configs:
            return None
        model_label = configs.get("type") or configs.get("model_type") or ""
        if isinstance(model_label, str) and " - " in model_label:
            model_label = model_label.split(" - ")[-1]
        return model_label or configs.get("model_type")

    def _format_loras(self, configs):
        loras = configs.get("activated_loras") or []
        if not loras:
            return None
        names = [os.path.basename(str(item)) for item in loras]
        preview = ", ".join(names[:4])
        if len(names) > 4:
            preview += f" (+{len(names) - 4} more)"
        multipliers = str(configs.get("loras_multipliers", "") or "").strip()
        if multipliers:
            preview += f" — multipliers: {multipliers[:80]}"
        return preview

    def _build_metadata_html(self, state, file_path, configs, library_entry=None):
        extra_rows = []
        if library_entry:
            tags = library_entry.get("tags") or []
            if tags:
                extra_rows.append(("Tags", ", ".join(tags)))
            if not library_entry.get("file_exists", True):
                extra_rows.append(("Source file", "Missing on disk"))

        if not configs or "seed" not in configs:
            creation = str(self.get_file_creation_date(file_path))
            creation = creation[: creation.rfind(".")] if "." in creation else creation
            rows = [
                ("File", os.path.basename(file_path)),
                ("Created", creation),
            ]
            if self.has_image_file_extension(file_path):
                width, height = Image.open(file_path).size
                rows.append(("Resolution", f"{width}x{height}"))
            elif self.has_video_file_extension(file_path):
                fps, width, height, frames = self.get_video_info(file_path)
                rows.append(("Resolution", f"{width}x{height}"))
                rows.append(("Frames", f"{frames} ({frames / max(fps, 1):.1f}s @ {round(fps)} fps)"))

            rows.extend(extra_rows)
            body = "".join(
                f"<tr><td>{html.escape(label)}</td>"
                f"<td><b>{html.escape(str(value))}</b></td>"
                f"<td><button class='pm-copy-btn' onclick=\"copyPromptManagerValue(this)\" title='Copy'>📋</button></td></tr>"
                for label, value in rows
                if value is not None
            )
            return (
                "<div class='pm-metadata'>"
                "<p class='pm-hint'>No WanGP generation metadata found for this file.</p>"
                f"<table id='pm_info' width='100%'>{body}</table></div>"
            )

        field_values = {
            "model": self._format_model_name(configs),
            "prompt": (configs.get("prompt") or "")[:1024] or None,
            "seed": configs.get("seed"),
            "resolution": configs.get("resolution"),
            "steps": configs.get("num_inference_steps"),
            "cfg": configs.get("guidance_scale"),
            "loras": self._format_loras(configs),
        }

        rows = []
        for field_id, label in FIELD_LABELS.items():
            value = field_values.get(field_id)
            if value is None or value == "":
                continue
            display_str = str(value)
            if field_id == "prompt" and len(display_str) > 120:
                escaped_full = html.escape(display_str).replace("\n", "<br>")
                display = (
                    f"<span class='pm-prompt-wrapper'>"
                    f"<span class='pm-prompt-text collapsed'><b>{escaped_full}</b></span>"
                    f"<button class='pm-prompt-toggle' onclick='event.stopPropagation(); togglePMPrompt(this);'>...</button>"
                    f"</span>"
                )
                rows.append(
                    f"<tr class='pm-clickable' onclick=\"applyPromptManagerField('{field_id}')\" "
                    f"title='Click to use this {html.escape(label)} in the generator'>"
                    f"<td>{html.escape(label)} ▸</td><td>{display}</td>"
                    f"<td><button class='pm-copy-btn' onclick=\"event.stopPropagation(); copyPromptManagerValue(this)\" "
                    f"title='Copy'>📋</button></td></tr>"
                )
            else:
                display = html.escape(display_str).replace("\n", "<br>")
                rows.append(
                    f"<tr class='pm-clickable' onclick=\"applyPromptManagerField('{field_id}')\" "
                    f"title='Click to use this {html.escape(label)} in the generator'>"
                    f"<td>{html.escape(label)} ▸</td><td><b>{display}</b></td>"
                    f"<td><button class='pm-copy-btn' onclick=\"event.stopPropagation(); copyPromptManagerValue(this)\" "
                    f"title='Copy'>📋</button></td></tr>"
                )

        for label, value in extra_rows:
            rows.append(
                f"<tr><td>{html.escape(label)}</td><td><b>{html.escape(str(value))}</b></td>"
                f"<td><button class='pm-copy-btn' onclick=\"copyPromptManagerValue(this)\" title='Copy'>📋</button></td></tr>"
            )

        if not rows:
            return "<div class='pm-metadata'><p class='placeholder'>Metadata found but no reusable fields.</p></div>"

        return (
            "<div class='pm-metadata'>"
            "<p class='pm-hint'>Click a row to send it to the generator, or use 📋 to copy.</p>"
            f"<table id='pm_info' width='100%'>{''.join(rows)}</table></div>"
        )

    def _detail_panel_defaults(self):
        return {
            self.metadata_html: gr.HTML(
                value="<div class='pm-metadata'><p class='placeholder'>Select a file to view metadata.</p></div>"
            ),
            self.preview_row: gr.Column(visible=False),
            self.video_preview: gr.Video(value=None, visible=False),
            self.image_preview: gr.Image(value=None, visible=False),
            self.variation_row: gr.Column(visible=False),
            self.library_row: gr.Column(visible=False),
            self.save_library_btn: gr.Button(visible=False),
            self.remove_library_btn: gr.Button(visible=False),
            self.library_tags: gr.Textbox(value=""),
            self.generate_row: gr.Column(visible=False),
            self.generate_btn: gr.Button(visible=False),
            self.generate_cancel_btn: gr.Button(visible=False),
            self.generate_output_row: gr.Column(visible=False),
            self.generate_preview_image: gr.Image(value=None, visible=False),
            self.generate_preview_video: gr.Video(value=None, visible=False),
            self.use_all_btn: gr.Button(visible=False, interactive=False),
        }

    def update_detail_panel(self, file_path, state):
        updates = self._detail_panel_defaults()
        if not file_path:
            return updates

        configs = self._load_configs(state, file_path)
        preview_path = self._resolve_preview_path(file_path)
        is_library = self._is_library_path(file_path)
        library_entry = self._get_library_entry(file_path) if is_library else None
        saved_entry = None
        if not is_library and preview_path:
            saved_entry = find_by_source_path(self._get_library_entries(), os.path.abspath(preview_path))

        display_path = preview_path or file_path
        updates[self.metadata_html] = gr.HTML(
            value=self._build_metadata_html(state, display_path, configs, library_entry)
        )

        if preview_path and self.has_video_file_extension(preview_path):
            updates[self.preview_row] = gr.Column(visible=True)
            updates[self.video_preview] = gr.Video(value=preview_path, visible=True)
            updates[self.image_preview] = gr.Image(value=None, visible=False)
        elif preview_path and self.has_image_file_extension(preview_path):
            updates[self.preview_row] = gr.Column(visible=True)
            updates[self.image_preview] = gr.Image(value=Image.open(preview_path), visible=True)
            updates[self.video_preview] = gr.Video(value=None, visible=False)

        if configs and "seed" in configs:
            updates[self.use_all_btn] = gr.Button(visible=True, interactive=True)
            updates[self.variation_row] = gr.Column(visible=True)
            updates[self.library_row] = gr.Column(visible=True)
            updates[self.generate_row] = gr.Column(visible=True)
            updates[self.generate_btn] = gr.Button(visible=True)
            if is_library:
                updates[self.remove_library_btn] = gr.Button(visible=True)
                updates[self.library_tags] = gr.Textbox(
                    value=", ".join(library_entry.get("tags", [])) if library_entry else ""
                )
            elif saved_entry:
                updates[self.remove_library_btn] = gr.Button(visible=True)
                updates[self.library_tags] = gr.Textbox(value=", ".join(saved_entry.get("tags", [])))
            else:
                updates[self.save_library_btn] = gr.Button(visible=True)

        return updates

    def save_to_library(self, file_path, state, tags_text):
        if not file_path or self._is_library_path(file_path):
            gr.Warning("Select an output file to save.")
            return self.update_detail_panel(file_path, state)

        entry_data = self._library_entry_from_file(state, file_path, tags_text)
        if not entry_data:
            gr.Warning("This file has no reusable WanGP metadata to save.")
            return self.update_detail_panel(file_path, state)

        upsert_entry(self.plugin_dir, entry_data)
        gr.Info("Saved to library.")
        return self.update_detail_panel(file_path, state)

    def remove_from_library(self, file_path, state):
        entry_id = ""
        if self._is_library_path(file_path):
            entry_id = self._parse_library_id(file_path)
        elif file_path:
            saved = find_by_source_path(self._get_library_entries(), os.path.abspath(file_path))
            entry_id = saved.get("id") if saved else ""

        if not entry_id or not remove_by_id(self.plugin_dir, entry_id):
            gr.Warning("Could not remove from library.")
            return self.update_detail_panel(file_path, state)

        gr.Info("Removed from library.")
        return self._detail_panel_defaults()

    def apply_variation(self, file_path, state, mode):
        if not file_path:
            gr.Warning("No file selected.")
            return *self._no_model_updates(), gr.update(), gr.update()

        if mode == "same_seed":
            return self.apply_all_settings(file_path, state)

        if mode == "new_seed":
            result = self.apply_all_settings(file_path, state)
            model_type = self.get_state_model_type(state)
            settings = self.get_model_settings(state, model_type) or self.get_default_settings(model_type) or {}
            settings["seed"] = -1
            self.set_model_settings(state, model_type, settings)
            gr.Info("Variation loaded with a new random seed.")
            return result

        if mode == "prompt_new_seed":
            configs = self._load_configs(state, file_path)
            if not configs or configs.get("prompt") is None:
                gr.Warning("No prompt found for this item.")
                return *self._no_model_updates(), gr.update(), gr.update()
            model_type, settings = self._current_settings(state)
            settings["prompt"] = configs["prompt"]
            settings["seed"] = -1
            self.set_model_settings(state, model_type, settings)
            gr.Info("Prompt applied with a new random seed.")
            return *self._no_model_updates(), *self._goto_generator()

        gr.Warning("Unknown variation mode.")
        return *self._no_model_updates(), gr.update(), gr.update()

    def _current_settings(self, state):
        model_type = self.get_state_model_type(state)
        settings = self.get_model_settings(state, model_type)
        defaults = self.get_default_settings(model_type) or {}
        if settings is None:
            return model_type, dict(defaults)
        return model_type, {**defaults, **settings}

    def _no_model_updates(self):
        return gr.update(), gr.update()

    def _goto_generator(self):
        return gr.Tabs(selected="video_gen"), self.get_unique_id()

    def apply_field_action(self, action, state):
        if not action or "||" not in action:
            return *self._no_model_updates(), *self._goto_generator()

        field, file_path = action.split("||", 1)
        field = field.strip()
        file_path = file_path.strip()
        configs = self._load_configs(state, file_path)

        if not configs or "seed" not in configs:
            gr.Warning("No reusable WanGP metadata found for this file.")
            return *self._no_model_updates(), gr.update(), gr.update()

        if field == "all":
            return self.apply_all_settings(file_path, state)

        current_model_type = self.get_state_model_type(state)
        model_type, settings = self._current_settings(state)

        if field == "model":
            target_model_type = configs.get("model_type") or current_model_type
            state["model_type"] = target_model_type
            gr.Info(f"Switched to model '{self._format_model_name(configs) or target_model_type}'.")
            dropdowns = self.generate_dropdown_model_list(target_model_type, state)
            return dropdowns[0], dropdowns[2], *self._goto_generator()

        if field == "prompt" and configs.get("prompt") is not None:
            settings["prompt"] = configs["prompt"]
            label = "Prompt"
        elif field == "seed" and configs.get("seed") is not None:
            settings["seed"] = configs["seed"]
            label = "Seed"
        elif field == "resolution" and configs.get("resolution"):
            settings["resolution"] = configs["resolution"]
            label = "Resolution"
        elif field == "steps" and configs.get("num_inference_steps") is not None:
            settings["num_inference_steps"] = configs["num_inference_steps"]
            label = "Steps"
        elif field == "cfg" and configs.get("guidance_scale") is not None:
            settings["guidance_scale"] = configs["guidance_scale"]
            label = "CFG"
        elif field == "loras":
            settings["activated_loras"] = list(configs.get("activated_loras") or [])
            settings["loras_multipliers"] = configs.get("loras_multipliers", "")
            label = "LoRAs"
        else:
            gr.Warning(f"Field '{field}' is not available in this file's metadata.")
            return *self._no_model_updates(), gr.update(), gr.update()

        self.set_model_settings(state, model_type, settings)
        gr.Info(f"{label} applied from '{os.path.basename(file_path)}'.")
        return *self._no_model_updates(), *self._goto_generator()

    def _prepare_generation_settings(self, file_path, state):
        if not file_path:
            return None

        configs = self._load_configs(state, file_path)
        if not configs:
            return None

        preview_path = self._resolve_preview_path(file_path)
        if not preview_path and not self._is_library_path(file_path):
            preview_path = file_path

        current_model_type = self.get_state_model_type(state)
        target_model_type = configs.get("model_type", current_model_type)
        if self.are_model_types_compatible(target_model_type, current_model_type):
            target_model_type = current_model_type
        configs["model_type"] = target_model_type

        first_frame = last_frame = None
        if preview_path and self.has_video_file_extension(preview_path):
            first_frame = self.get_video_frame(preview_path, 0, return_PIL=True)
            _, _, _, frame_count = self.get_video_info(preview_path)
            if frame_count > 1:
                last_frame = self.get_video_frame(preview_path, frame_count - 1, return_PIL=True)
        elif preview_path and self.has_image_file_extension(preview_path):
            first_frame = Image.open(preview_path)

        allowed_prompts = self.get_model_def(target_model_type).get("image_prompt_types_allowed", "")
        configs = {**self.get_default_settings(target_model_type), **configs}
        if first_frame:
            updated_prompts = (
                self.add_to_sequence(configs.get("image_prompt_type", ""), "S")
                if "S" in allowed_prompts
                else configs.get("image_prompt_type", "")
            )
            configs["image_start"] = [(first_frame, "First Frame")]
            if last_frame and "E" in allowed_prompts:
                updated_prompts = self.add_to_sequence(updated_prompts, "E")
                configs["image_end"] = [(last_frame, "Last Frame")]
            configs["image_prompt_type"] = updated_prompts

        return configs

    def apply_all_settings(self, file_path, state):
        if not file_path:
            gr.Warning("No file selected.")
            return *self._no_model_updates(), gr.update(), gr.update()

        configs = self._prepare_generation_settings(file_path, state)
        if not configs:
            gr.Warning("No settings found for this item.")
            return *self._no_model_updates(), gr.update(), gr.update()

        preview_path = self._resolve_preview_path(file_path)
        if not preview_path and not self._is_library_path(file_path):
            preview_path = file_path
        current_model_type = self.get_state_model_type(state)
        target_model_type = configs.get("model_type")

        self.set_model_settings(state, target_model_type, configs)
        label = os.path.basename(preview_path or file_path)
        if self._is_library_path(file_path):
            entry = self._get_library_entry(file_path)
            label = entry.get("basename", "saved prompt") if entry else "saved prompt"
        gr.Info(f"All settings from '{label}' sent to the generator.")

        if target_model_type == current_model_type:
            model_updates = self._no_model_updates()
        else:
            dropdowns = self.generate_dropdown_model_list(target_model_type, state)
            model_updates = (dropdowns[0], dropdowns[2])

        return *model_updates, *self._goto_generator()
