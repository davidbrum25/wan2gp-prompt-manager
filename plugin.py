import html
import json
import os
import re

import gradio as gr
from PIL import Image

from shared.utils.plugins import WAN2GPPlugin

from .media_utils import get_thumbnails_in_batch

FIELD_LABELS = {
    "model": "Model",
    "prompt": "Prompt",
    "seed": "Seed",
    "resolution": "Resolution",
    "steps": "Steps",
    "cfg": "CFG",
    "loras": "LoRAs",
}


class PromptManagerPlugin(WAN2GPPlugin):
    def __init__(self):
        super().__init__()
        self.loaded_once = False

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

    def create_prompt_manager_ui(self):
        css = """
            #pm-layout {
                display: flex;
                gap: 16px;
                min-height: 75vh;
                align-items: flex-start;
            }
            #pm-grid-container {
                flex: 3;
                max-height: 80vh;
                overflow-y: auto;
                border: 1px solid var(--border-color-primary);
                padding: 10px;
                background-color: var(--background-fill-secondary);
                border-radius: 8px;
            }
            #pm-detail-panel {
                flex: 1;
                border: 1px solid var(--border-color-primary);
                padding: 15px;
                background-color: var(--background-fill-primary);
                border-radius: 8px;
                min-width: 280px;
            }
            .pm-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
                gap: 16px;
            }
            .pm-item {
                position: relative;
                cursor: pointer;
                border: 2px solid transparent;
                border-radius: 8px;
                overflow: hidden;
                aspect-ratio: 4 / 5;
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
                flex-grow: 1;
                background-color: var(--panel-background-fill);
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
            }
            .pm-item-thumb img, .pm-item-thumb video {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
            .pm-item-name {
                padding: 4px 8px;
                font-size: 12px;
                text-align: center;
                background-color: var(--panel-background-fill);
                color: var(--body-text-color);
                white-space: normal;
                word-break: break-word;
                border-top: 1px solid var(--border-color-primary);
                min-height: 3.2em;
                display: flex;
                align-items: center;
                justify-content: center;
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
                width: 1%;
            }
            .pm-clickable td:last-child {
                font-weight: bold;
            }
            .pm-hint {
                font-size: 12px;
                color: var(--body-text-color-subdued);
                margin-bottom: 10px;
            }
            #pm_info TR, #pm_info TD {
                background-color: transparent;
                color: inherit;
                padding: 6px 4px;
                border: 0 !important;
                font-size: 12px;
            }
        """

        js = """
            function() {
                window.selectPromptManagerItem = function(event, element) {
                    if (element.classList.contains('pm-folder')) return;

                    const grid = element.closest('.pm-grid');
                    const selectedInput = document.querySelector('#pm-selected-file textarea');
                    if (!grid || !selectedInput) return;

                    if (!event.ctrlKey && !event.metaKey) {
                        grid.querySelectorAll('.pm-item.selected').forEach(el => {
                            if (el !== element) el.classList.remove('selected');
                        });
                    }
                    element.classList.toggle('selected');
                    const selected = Array.from(grid.querySelectorAll('.pm-item.selected:not(.pm-folder)'));
                    const path = selected.length === 1 ? selected[0].dataset.path : '';
                    selectedInput.value = path;
                    selectedInput.dispatchEvent(new Event('input', { bubbles: true }));
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
            }
        """

        with gr.Blocks() as blocks:
            gr.HTML(value=f"<style>{css}</style>")
            blocks.load(fn=None, js=js)
            with gr.Column(elem_id="prompt_manager_tab_container"):
                gr.Markdown(
                    "### Prompt Manager\n"
                    "Browse your outputs and click any metadata row to send that value to the Media Generator. "
                    "Works with both images and videos."
                )
                with gr.Row():
                    self.refresh_btn = gr.Button("Refresh Files", variant="secondary")
                with gr.Row(elem_id="pm-layout"):
                    self.grid_html = gr.HTML(
                        value="<div class='pm-grid'><p class='placeholder'>Click 'Refresh Files' to load your outputs.</p></div>",
                        elem_id="pm-grid-container",
                    )
                    with gr.Column(elem_id="pm-detail-panel"):
                        with gr.Column(visible=False) as self.preview_row:
                            self.video_preview = gr.Video(label="Preview", interactive=True, height=220, visible=False)
                            self.image_preview = gr.Image(label="Preview", interactive=False, height=220, visible=False)
                        self.metadata_html = gr.HTML(
                            value="<div class='pm-metadata'><p class='placeholder'>Select a file to view metadata.</p></div>"
                        )
                        self.use_all_btn = gr.Button(
                            "Use All Settings in Generator",
                            variant="primary",
                            interactive=False,
                            visible=False,
                        )

                self.selected_file = gr.Text(visible=False, elem_id="pm-selected-file")
                self.current_dir = gr.Text(visible=False, elem_id="pm-current-dir")
                self.field_action = gr.Text(visible=False, elem_id="pm-field-action")

        grid_outputs = [
            self.grid_html,
            self.selected_file,
            self.metadata_html,
            self.preview_row,
            self.video_preview,
            self.image_preview,
            self.use_all_btn,
            self.current_dir,
        ]
        no_grid_updates = {comp: gr.update() for comp in grid_outputs}

        def on_tab_select(current_state, current_dir, evt: gr.SelectData):
            if evt.value == "Prompt Manager" and not self.loaded_once:
                self.loaded_once = True
                return self.list_media_files(current_state, current_dir)
            return no_grid_updates

        self.main_tabs.select(
            fn=on_tab_select,
            inputs=[self.state, self.current_dir],
            outputs=grid_outputs,
        )

        self.refresh_btn.click(
            fn=self.list_media_files,
            inputs=[self.state, self.current_dir],
            outputs=grid_outputs,
        )

        self.current_dir.change(
            fn=self.list_media_files,
            inputs=[self.state, self.current_dir],
            outputs=grid_outputs,
            show_progress="hidden",
        )

        detail_outputs = [
            self.metadata_html,
            self.preview_row,
            self.video_preview,
            self.image_preview,
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

        return blocks

    def _output_roots(self):
        save_path = os.path.abspath(self.server_config.get("save_path", "outputs"))
        image_save_path = os.path.abspath(self.server_config.get("image_save_path", "outputs"))
        roots = []
        for path in (save_path, image_save_path):
            if path and os.path.isdir(path) and path not in roots:
                roots.append(path)
        return roots

    def _is_within_roots(self, path, roots):
        abs_path = os.path.abspath(path)
        for root in roots:
            try:
                if os.path.commonpath([abs_path, root]) == root:
                    return True
            except Exception:
                pass
        return False

    def list_media_files(self, current_state, current_dir=""):
        roots = self._output_roots()
        cur = (current_dir or "").strip()
        cur_abs = os.path.abspath(cur) if cur else ""

        if cur_abs and (not os.path.isdir(cur_abs) or not self._is_within_roots(cur_abs, roots)):
            cur_abs = ""

        folder_items = []
        file_items = []
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
            file_items.append(abs_path)

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
        file_items.sort(key=os.path.getctime, reverse=True)

        thumb_targets = [
            path
            for path in file_items
            if self.has_video_file_extension(path) or self.has_image_file_extension(path)
        ]
        thumbnails = get_thumbnails_in_batch(thumb_targets)

        items_html = ""
        for folder in folder_items:
            safe_path = json.dumps(folder["path"], ensure_ascii=False)
            items_html += f"""
            <div class="pm-item pm-folder" data-path={safe_path} ondblclick="openPromptManagerFolder(event, this)">
                <div class="pm-item-thumb" style="display:flex;align-items:center;justify-content:center;font-size:42px;">📁</div>
                <div class="pm-item-name" title="{html.escape(folder['name'])}">{html.escape(folder['name'])}</div>
            </div>
            """

        for file_path in file_items:
            basename = os.path.basename(file_path)
            display_name = basename
            match = re.search(
                r"_seed\d+_(.+)\.(mp4|jpg|jpeg|png|webp|gif)$",
                basename,
                re.IGNORECASE,
            )
            if match:
                display_name = match.group(1)

            is_video = self.has_video_file_extension(file_path)
            base64_thumb = thumbnails.get(os.path.abspath(file_path))
            if base64_thumb:
                thumb_html = f'<img src="data:image/jpeg;base64,{base64_thumb}" alt="thumb">'
            elif is_video:
                thumb_html = f'<video muted preload="metadata" src="/gradio_api/file={file_path}#t=0.5"></video>'
            else:
                thumb_html = f'<img src="/gradio_api/file={file_path}" alt="thumb">'

            safe_path = json.dumps(file_path, ensure_ascii=False)
            items_html += f"""
            <div class="pm-item" data-path={safe_path} onclick="selectPromptManagerItem(event, this)">
                <div class="pm-item-thumb">{thumb_html}</div>
                <div class="pm-item-name" title="{html.escape(basename)}">{html.escape(display_name)}</div>
            </div>
            """

        empty_html = "<div class='pm-grid'><p class='placeholder'>No images or videos found in output folders.</p></div>"
        grid_html = f"<div class='pm-grid'>{items_html}</div>" if items_html else empty_html
        clear_metadata = (
            "<div class='pm-metadata'><p class='placeholder'>Select a file to view metadata.</p></div>"
        )

        return {
            self.grid_html: grid_html,
            self.selected_file: "",
            self.metadata_html: clear_metadata,
            self.preview_row: gr.Column(visible=False),
            self.video_preview: gr.Video(value=None, visible=False),
            self.image_preview: gr.Image(value=None, visible=False),
            self.use_all_btn: gr.Button(visible=False, interactive=False),
            self.current_dir: cur_abs if cur_abs else "",
        }

    def _load_configs(self, state, file_path):
        if not file_path:
            return None
        configs, _, _ = self.get_settings_from_file(state, file_path, True, True, True)
        return configs

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

    def _build_metadata_html(self, state, file_path, configs):
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

            body = "".join(
                f"<tr><td>{html.escape(label)}</td><td><b>{html.escape(str(value))}</b></td></tr>"
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
            display = html.escape(str(value)).replace("\n", "<br>")
            rows.append(
                f"<tr class='pm-clickable' onclick=\"applyPromptManagerField('{field_id}')\" "
                f"title='Click to use this {html.escape(label)} in the generator'>"
                f"<td>{html.escape(label)} ▸</td><td><b>{display}</b></td></tr>"
            )

        if not rows:
            return "<div class='pm-metadata'><p class='placeholder'>Metadata found but no reusable fields.</p></div>"

        return (
            "<div class='pm-metadata'>"
            "<p class='pm-hint'>Click any row to send that value to the Media Generator.</p>"
            f"<table id='pm_info' width='100%'>{''.join(rows)}</table></div>"
        )

    def update_detail_panel(self, file_path, state):
        updates = {
            self.metadata_html: gr.HTML(
                value="<div class='pm-metadata'><p class='placeholder'>Select a file to view metadata.</p></div>"
            ),
            self.preview_row: gr.Column(visible=False),
            self.video_preview: gr.Video(value=None, visible=False),
            self.image_preview: gr.Image(value=None, visible=False),
            self.use_all_btn: gr.Button(visible=False, interactive=False),
        }

        if not file_path:
            return updates

        configs = self._load_configs(state, file_path)
        updates[self.metadata_html] = gr.HTML(value=self._build_metadata_html(state, file_path, configs))
        updates[self.preview_row] = gr.Column(visible=True)

        if self.has_video_file_extension(file_path):
            updates[self.video_preview] = gr.Video(value=file_path, visible=True)
            updates[self.image_preview] = gr.Image(value=None, visible=False)
        elif self.has_image_file_extension(file_path):
            updates[self.image_preview] = gr.Image(value=Image.open(file_path), visible=True)
            updates[self.video_preview] = gr.Video(value=None, visible=False)

        if configs and "seed" in configs:
            updates[self.use_all_btn] = gr.Button(visible=True, interactive=True)

        return updates

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

    def apply_all_settings(self, file_path, state):
        if not file_path:
            gr.Warning("No file selected.")
            return *self._no_model_updates(), gr.update(), gr.update()

        configs, _, _ = self.get_settings_from_file(state, file_path, True, True, True)
        if not configs:
            gr.Warning("No settings found in this file.")
            return *self._no_model_updates(), gr.update(), gr.update()

        current_model_type = self.get_state_model_type(state)
        target_model_type = configs.get("model_type", current_model_type)
        if self.are_model_types_compatible(target_model_type, current_model_type):
            target_model_type = current_model_type
        configs["model_type"] = target_model_type

        first_frame = last_frame = None
        if self.has_video_file_extension(file_path):
            first_frame = self.get_video_frame(file_path, 0, return_PIL=True)
            _, _, _, frame_count = self.get_video_info(file_path)
            if frame_count > 1:
                last_frame = self.get_video_frame(file_path, frame_count - 1, return_PIL=True)
        elif self.has_image_file_extension(file_path):
            first_frame = Image.open(file_path)

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

        self.set_model_settings(state, target_model_type, configs)
        gr.Info(f"All settings from '{os.path.basename(file_path)}' sent to the generator.")

        if target_model_type == current_model_type:
            model_updates = self._no_model_updates()
        else:
            dropdowns = self.generate_dropdown_model_list(target_model_type, state)
            model_updates = (dropdowns[0], dropdowns[2])

        return *model_updates, *self._goto_generator()