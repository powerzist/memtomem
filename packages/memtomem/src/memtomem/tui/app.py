"""Textual application entry point for ``mm tui``."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.geometry import Size, Spacing
from textual.screen import ModalScreen, Screen
from textual.strip import Strip
from textual.widgets._option_list import OptionDoesNotExist, OptionList
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Input,
    ListItem,
    ListView,
    SelectionList,
    Static,
    Tab,
    Tabs,
)

from memtomem.tui.catalog import COMMAND_CATALOG
from memtomem.tui.clipboard import read_os_clipboard, write_os_clipboard
from memtomem.tui.init_flow import ADVANCED_STEPS, PRESETS, TuiInitState, detect_provider_dirs
from memtomem.tui.runtime import (
    Readiness,
    ReadinessState,
    TuiPaths,
    config_exists,
    inspect_readiness,
    initialize_tui_config,
    resolve_tui_paths,
    save_tui_config,
    tui_components,
)
from memtomem.tui.shared import TUI_CSS, BorderStyleMixin, PanelScroll
from memtomem.tui.terminal import (
    BorderStyle,
    detect_terminal_profile,
    has_ime_limitations,
    normalize_windows_console_buffer_width,
    windows_console_viewport_size,
)

if TYPE_CHECKING:
    from memtomem.models import SearchResult


@dataclass(frozen=True)
class SourceRow:
    path: Path
    chunks: int
    last_updated: str | None
    namespaces: str | None


@dataclass
class UiWidgetState:
    value: str | None = None


class SettingRow(Static, can_focus=True):
    """Focusable settings row."""


class SettingStep(Static, can_focus=True):
    """Small one-cell clickable settings control."""


class RootSelectionAction(Static, can_focus=True):
    """Compact action token for managed-root selection operations."""

    BINDINGS = [
        Binding("left,h", "previous", "Previous selection action", show=False),
        Binding("right,l", "next", "Next selection action", show=False),
        Binding("enter", "activate", "Activate selection action", show=False),
    ]

    def action_previous(self) -> None:
        move = getattr(self.app, "focus_panel_item_horizontal", None)
        if move is not None:
            move(-1)

    def action_next(self) -> None:
        move = getattr(self.app, "focus_panel_item_horizontal", None)
        if move is not None:
            move(1)

    async def action_activate(self) -> None:
        handle = getattr(self.app, "handle_button", None)
        if handle is not None and self.id is not None:
            await handle(self.id)


class MenuItem(Static, can_focus=True):
    """One item in the top menu bar."""

    async def _on_click(self, event: events.Click) -> None:
        prepare = getattr(self.app, "prepare_menu_item_click", None)
        if prepare is not None and not prepare(self):
            event.stop()
            return
        event.stop()
        handle = getattr(self.app, "handle_button", None)
        if handle is not None and self.id is not None:
            await handle(self.id)


class PanelButton(Button):
    """Button used inside the main/detail panel system."""

    async def _on_click(self, event: events.Click) -> None:
        prepare = getattr(self.app, "prepare_panel_button_click", None)
        if prepare is not None and not prepare(self):
            event.stop()
            return
        await super()._on_click(event)


class ModalButton(Button):
    """Button used inside modal screens."""


class ManagedRootsSelectionList(SelectionList[str]):
    """Selection list that renders roots with ASCII checkbox markers."""

    def _get_left_gutter_width(self) -> int:
        return len("[*] ")

    def render_line(self, y: int) -> Strip:
        line = OptionList.render_line(self, y)
        _, scroll_y = self.scroll_offset
        selection_index = scroll_y + y
        try:
            selection = self.get_option_at_index(selection_index)
        except OptionDoesNotExist:
            return line

        component_style = "selection-list--button"
        if selection.value in self._selected:
            component_style += "-selected"
        if self.highlighted == selection_index:
            component_style += "-highlighted"

        underlying_style = next(iter(line)).style or self.rich_style
        assert underlying_style is not None

        button_style = self.get_component_rich_style(component_style)
        side_style = Style.from_color(button_style.bgcolor, underlying_style.bgcolor)
        side_style += Style(meta={"option": selection_index})
        button_style += Style(meta={"option": selection_index})
        marker = "*" if selection.value in self._selected else " "

        return Strip(
            [
                Segment("[", style=side_style),
                Segment(marker, style=button_style),
                Segment("]", style=side_style),
                Segment(" ", style=underlying_style),
                *line,
            ]
        )


class InitScreen(BorderStyleMixin, Screen[TuiInitState | None]):
    """First-run gate shown before the main TUI is available."""

    CSS = TUI_CSS
    BINDINGS = [
        Binding("escape", "cancel", "Quit", priority=True),
        Binding("up,k", "focus_previous", "Previous", show=False, priority=True),
        Binding("down,j", "focus_next", "Next", show=False, priority=True),
        Binding("left,h", "focus_left", "Previous", show=False, priority=True),
        Binding("right,l", "focus_right", "Next", show=False, priority=True),
        Binding("enter", "activate", "Select", show=False, priority=True),
        Binding("page_up", "page_up", "Page up", show=False, priority=True),
        Binding("page_down", "page_down", "Page down", show=False, priority=True),
    ]

    def __init__(self, *, paths: TuiPaths, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.paths = paths
        self.border_style = border_style
        self.state = TuiInitState(
            memory_dir=str(paths.memories_path), db_path=str(paths.database_path)
        )
        self.state.apply_preset()
        self.step_index = 0
        self.detected_provider_dirs = detect_provider_dirs()
        self.model_button_values: dict[str, tuple[str, int]] = {}

    def compose(self) -> ComposeResult:
        with Container(classes="init-screen"):
            with Vertical(classes=f"modal-dialog init-dialog {self.border_class}".strip()):
                yield Static("Set up memtomem", classes="modal-title")
                yield Static("", id="init-step-title", classes="title")
                with Horizontal(id="init-layout"):
                    with Vertical(
                        id="init-main",
                        classes=f"section-panel main-section {self.border_class}".strip(),
                    ):
                        with PanelScroll(id="init-step-body", classes="section-body"):
                            yield Static("")
                    with Vertical(
                        id="init-detail",
                        classes=f"section-panel detail-section {self.border_class}".strip(),
                    ):
                        with PanelScroll(id="init-detail-body", classes="section-body"):
                            yield Static("Details", classes="title section-title")
                            yield Static("", id="init-detail-text")
                yield Static("", id="init-error", classes="error")
                with Horizontal(classes="modal-actions"):
                    yield ModalButton("Back", id="init-back", classes="action-button")
                    yield ModalButton("Next", id="init-next", classes="action-button cyan")
                    yield ModalButton("Quit", id="init-cancel", classes="action-button")

    async def on_mount(self) -> None:
        await self._render_step()

    async def _render_step(self) -> None:
        body = self.query_one("#init-step-body", PanelScroll)
        await body.remove_children()
        self.query_one("#init-error", Static).update("")
        back = self.query_one("#init-back", Button)
        next_button = self.query_one("#init-next", Button)
        back.disabled = self.step_index == 0

        steps = self.state.steps
        title = steps[self.step_index]
        self.query_one("#init-step-title", Static).update(
            f"Step {self.step_index + 1}/{len(steps)}  {title}"
        )
        next_button.label = "Initialize" if self.step_index == len(steps) - 1 else "Next"
        await self._mount_current_step(body)
        self._update_init_detail(None)
        if self.focused is None or not self.focused.is_mounted:
            next_button.focus()

    async def _choice(
        self, body: PanelScroll, label: str, button_id: str, selected: bool = False
    ) -> None:
        await body.mount(
            ModalButton(
                label,
                id=button_id,
                classes=f"choice-button {'cyan' if selected else ''}".strip(),
            )
        )

    async def _mount_current_step(self, body: PanelScroll) -> None:
        state = self.state
        title = state.steps[self.step_index]
        if title == "Setup style":
            for name, preset in PRESETS.items():
                await self._choice(
                    body,
                    preset.label,
                    f"init-preset-{name}",
                    state.mode == "preset" and state.preset_name == name,
                )
            await self._choice(
                body,
                "Advanced",
                "init-mode-advanced",
                state.mode == "advanced",
            )
            self.query_one(f"#init-preset-{state.preset_name}", Button).focus()
        elif title == "Embedding Provider":
            for value, label in (
                ("none", "Quick start"),
                ("onnx", "Local ONNX"),
                ("ollama", "Ollama"),
                ("openai", "OpenAI"),
            ):
                await self._choice(body, label, f"init-provider-{value}", state.provider == value)
            if state.provider == "onnx":
                models = (("all-MiniLM-L6-v2", 384), ("bge-small-en-v1.5", 384), ("bge-m3", 1024))
            elif state.provider == "ollama":
                models = (("nomic-embed-text", 768), ("bge-m3", 1024))
            elif state.provider == "openai":
                models = (("text-embedding-3-small", 1536), ("text-embedding-3-large", 3072))
            else:
                models = ()
            self.model_button_values.clear()
            for index, (model, dimension) in enumerate(models):
                button_id = f"init-model-{index}"
                self.model_button_values[button_id] = (model, dimension)
                await self._choice(
                    body, f"Model: {model} ({dimension}d)", button_id, state.model == model
                )
            if state.provider == "openai":
                await body.mount(
                    Input(
                        value=state.api_key,
                        placeholder="OpenAI API key",
                        password=True,
                        id="init-api-key",
                        classes="text-input",
                    )
                )
        elif title == "Reranker (optional)":
            await self._choice(body, "Disabled", "init-rerank-off", not state.rerank_enabled)
            await self._choice(
                body,
                "English",
                "init-rerank-en",
                state.rerank_enabled and "multilingual" not in state.rerank_model,
            )
            await self._choice(
                body,
                "Multilingual",
                "init-rerank-multi",
                state.rerank_enabled and "multilingual" in state.rerank_model,
            )
        elif title == "Memory Directory":
            await body.mount(
                Static("Where are the files you want to index?", classes="muted"),
                Input(value=state.memory_dir, id="init-memory-dir", classes="text-input"),
            )
            self.query_one("#init-memory-dir", Input).focus()
        elif title == "Provider Memory Folders":
            available = {key: paths for key, paths in self.detected_provider_dirs.items() if paths}
            if state.mode == "preset":
                preset = PRESETS[state.preset_name]
                state.provider_categories = set(available) if preset.autodetect_providers else set()
                await body.mount(
                    Static(
                        f"Auto-detected {sum(len(paths) for paths in available.values())} provider folder(s).",
                        classes="muted",
                    )
                )
            if not available:
                await body.mount(Static("No AI tool memory folders detected.", classes="muted"))
            for category, paths in available.items():
                await self._choice(
                    body,
                    f"{category} ({len(paths)} folder(s))",
                    f"init-provider-dir-{category}",
                    category in state.provider_categories,
                )
        elif title == "Storage":
            await body.mount(
                Input(
                    value=state.db_path,
                    placeholder="SQLite DB path",
                    id="init-db-path",
                    classes="text-input",
                )
            )
        elif title == "Namespace":
            await self._choice(
                body, "Auto-assign namespace from folder name", "init-auto-ns", state.enable_auto_ns
            )
            await self._choice(
                body, "Use default namespace only", "init-manual-ns", not state.enable_auto_ns
            )
            await body.mount(
                Input(
                    value=state.default_ns,
                    placeholder="Default namespace",
                    id="init-default-ns",
                    classes="text-input",
                )
            )
        elif title == "Search":
            await body.mount(
                Input(
                    value=str(state.top_k),
                    placeholder="Results per search",
                    id="init-top-k",
                    classes="text-input",
                )
            )
            await self._choice(body, "Time-decay enabled", "init-decay-on", state.decay_enabled)
            await self._choice(
                body, "Time-decay disabled", "init-decay-off", not state.decay_enabled
            )
        elif title == "Language":
            await self._choice(
                body,
                "Unicode tokenizer",
                "init-tokenizer-unicode61",
                state.tokenizer == "unicode61",
            )
            await self._choice(
                body,
                "Korean tokenizer (kiwipiepy)",
                "init-tokenizer-kiwipiepy",
                state.tokenizer == "kiwipiepy",
            )
        elif title == "Claude Code Hooks":
            detected = (Path.home() / ".claude").is_dir()
            await body.mount(
                Static(
                    "Claude Code detected."
                    if detected
                    else "Claude Code not detected; this step will be skipped.",
                    classes="muted",
                )
            )
            await self._choice(body, "Configure hooks", "init-hooks-on", state.settings_hooks)
            await self._choice(body, "Skip hooks", "init-hooks-off", not state.settings_hooks)
        elif title == "Connect to AI Editor":
            for value, label in (
                (1, "Claude Code"),
                (2, "Generate .mcp.json"),
                (3, "Skip"),
                (4, "Kimi CLI"),
            ):
                await self._choice(body, label, f"init-mcp-{value}", state.mcp_choice == value)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if await self._handle_choice(button_id):
            await self._render_step()
            return
        if button_id == "init-back":
            self._capture_inputs()
            if self.step_index > 0:
                self.step_index -= 1
            await self._render_step()
            return
        if button_id == "init-cancel":
            self.dismiss(None)
            return
        if button_id != "init-next":
            return
        if not self._capture_inputs():
            return
        if self.step_index < len(self.state.steps) - 1:
            self.step_index += 1
            await self._render_step()
            return
        self.state.provider_dirs = [
            str(path)
            for category in self.state.provider_categories
            for path in self.detected_provider_dirs.get(category, [])
        ]
        self.dismiss(self.state)

    async def _handle_choice(self, button_id: str) -> bool:
        state = self.state
        if button_id.startswith("init-preset-"):
            state.mode = "preset"
            state.preset_name = button_id.removeprefix("init-preset-")  # type: ignore[assignment]
            state.apply_preset()
        elif button_id == "init-mode-advanced":
            state.mode = "advanced"
            self.step_index = 0
        elif button_id.startswith("init-provider-") and not button_id.startswith(
            "init-provider-dir-"
        ):
            state.provider = button_id.removeprefix("init-provider-")
            defaults = {
                "none": ("", 0),
                "onnx": ("all-MiniLM-L6-v2", 384),
                "ollama": ("nomic-embed-text", 768),
                "openai": ("text-embedding-3-small", 1536),
            }
            state.model, state.dimension = defaults[state.provider]
        elif button_id in self.model_button_values:
            state.model, state.dimension = self.model_button_values[button_id]
        elif button_id.startswith("init-provider-dir-"):
            category = button_id.removeprefix("init-provider-dir-")
            state.provider_categories.symmetric_difference_update({category})
        elif button_id.startswith("init-rerank-"):
            value = button_id.removeprefix("init-rerank-")
            state.rerank_enabled = value != "off"
            state.rerank_model = (
                "jinaai/jina-reranker-v2-base-multilingual"
                if value == "multi"
                else "Xenova/ms-marco-MiniLM-L-6-v2"
            )
        elif button_id in {"init-auto-ns", "init-manual-ns"}:
            state.enable_auto_ns = button_id == "init-auto-ns"
        elif button_id in {"init-decay-on", "init-decay-off"}:
            state.decay_enabled = button_id == "init-decay-on"
        elif button_id.startswith("init-tokenizer-"):
            state.tokenizer = button_id.removeprefix("init-tokenizer-")
        elif button_id in {"init-hooks-on", "init-hooks-off"}:
            state.settings_hooks = button_id == "init-hooks-on"
        elif button_id.startswith("init-mcp-"):
            state.mcp_choice = int(button_id.removeprefix("init-mcp-"))
        else:
            return False
        return True

    def _capture_inputs(self) -> bool:
        title = self.state.steps[self.step_index]
        try:
            if title == "Memory Directory":
                value = self.query_one("#init-memory-dir", Input).value.strip()
                if not value:
                    raise ValueError("Enter a memory directory.")
                self.state.memory_dir = value
            elif title == "Embedding Provider" and self.state.provider == "openai":
                self.state.api_key = self.query_one("#init-api-key", Input).value.strip()
                if not self.state.api_key:
                    raise ValueError("Enter an OpenAI API key.")
            elif title == "Storage":
                self.state.db_path = self.query_one("#init-db-path", Input).value.strip()
            elif title == "Namespace":
                self.state.default_ns = (
                    self.query_one("#init-default-ns", Input).value.strip() or "default"
                )
            elif title == "Search":
                self.state.top_k = int(self.query_one("#init-top-k", Input).value)
                if self.state.top_k <= 0:
                    raise ValueError("Results per search must be positive.")
        except (ValueError, NoMatches) as exc:
            self.query_one("#init-error", Static).update(str(exc))
            return False
        return True

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_focus_previous(self) -> None:
        self.focus_previous()

    def action_focus_next(self) -> None:
        self.focus_next()

    def action_focus_left(self) -> None:
        focused = self.focused
        if isinstance(focused, Input):
            focused.action_cursor_left()
        elif getattr(focused, "id", None) == "init-next":
            self.query_one("#init-back", Button).focus()
        elif getattr(focused, "id", None) == "init-cancel":
            self.query_one("#init-next", Button).focus()
        else:
            self.focus_previous()

    def action_focus_right(self) -> None:
        focused = self.focused
        if isinstance(focused, Input):
            focused.action_cursor_right()
        elif getattr(focused, "id", None) == "init-back":
            self.query_one("#init-next", Button).focus()
        elif getattr(focused, "id", None) == "init-next":
            self.query_one("#init-cancel", Button).focus()
        else:
            self.focus_next()

    def action_activate(self) -> None:
        focused = self.focused
        if isinstance(focused, Button):
            focused.press()
        elif isinstance(focused, Input):
            self.query_one("#init-next", Button).press()

    def action_page_up(self) -> None:
        self.query_one("#init-step-body", PanelScroll).scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        self.query_one("#init-step-body", PanelScroll).scroll_page_down(animate=False)

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        self._update_init_detail(getattr(event.widget, "id", None))

    def _update_init_detail(self, widget_id: str | None) -> None:
        try:
            detail = self.query_one("#init-detail-text", Static)
        except NoMatches:
            return
        descriptions = {
            "init-preset-minimal": PRESETS["minimal"].description,
            "init-preset-english": PRESETS["english"].description,
            "init-preset-korean": PRESETS["korean"].description,
            "init-mode-advanced": "Configure every option through the full 10-step wizard.",
            "init-provider-none": "BM25 keyword search only. No model download is required.",
            "init-provider-onnx": "Local dense embeddings through fastembed ONNX.",
            "init-provider-ollama": "Use a locally running Ollama server for embeddings.",
            "init-provider-openai": "Use OpenAI cloud embeddings. An API key is required.",
            "init-rerank-off": "Skip cross-encoder reranking.",
            "init-rerank-en": "English cross-encoder reranker.",
            "init-rerank-multi": "Multilingual reranker for Korean and mixed-language memory.",
            "init-auto-ns": "Derive namespaces from folder names automatically.",
            "init-manual-ns": "Use the configured default namespace.",
            "init-decay-on": "Older memories gradually receive a lower search rank.",
            "init-decay-off": "Do not change rank based on memory age.",
            "init-tokenizer-unicode61": "General Unicode tokenizer for most languages.",
            "init-tokenizer-kiwipiepy": "Korean-aware word splitting. Requires the Korean extra.",
            "init-hooks-on": "Create and synchronize memtomem-managed Claude Code hooks.",
            "init-hooks-off": "Leave Claude Code hook settings unchanged.",
            "init-mcp-1": "Register memtomem in Claude Code at user scope.",
            "init-mcp-2": "Write a project-scoped .mcp.json.",
            "init-mcp-3": "Do not configure an editor connection during init.",
            "init-mcp-4": "Write the memtomem entry to the Kimi CLI MCP configuration.",
            "init-back": "Return to the previous interactive init step.",
            "init-next": "Validate this step and continue.",
            "init-cancel": "Cancel initialization and exit.",
        }
        if widget_id and widget_id.startswith("init-model-"):
            model = self.model_button_values.get(widget_id)
            text = f"Use {model[0]} with {model[1]} dimensions." if model else "Embedding model."
        elif widget_id and widget_id.startswith("init-provider-dir-"):
            category = widget_id.removeprefix("init-provider-dir-")
            paths = self.detected_provider_dirs.get(category, [])
            text = f"Include {len(paths)} detected {category} folder(s) in search."
        else:
            text = descriptions.get(
                widget_id or "", f"Configure {self.state.steps[self.step_index]}."
            )
        detail.update(text)


class KeybindingsScreen(BorderStyleMixin, ModalScreen[None]):
    """Modal help screen for keyboard shortcuts."""

    CSS = TUI_CSS

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close", show=False),
        Binding("up,k", "item_previous", "Previous item", show=False, priority=True),
        Binding("down,j", "item_next", "Next item", show=False, priority=True),
        Binding("page_up", "page_up", "Page up", show=False),
        Binding("page_down", "page_down", "Page down", show=False),
    ]

    def __init__(self, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.border_style = border_style

    def compose(self) -> ComposeResult:
        body = "\n".join(
            [
                "Navigation",
                "  Up/k            Move up within the current panel",
                "  Down/j          Move down within the current panel",
                "  PgUp/PgDn       Scroll the current panel by one page",
                "  Left/Right, h/l Move within the current section",
                "  F2/F3/F4        Focus menu/main/details",
                "  Tab/Shift+Tab   Move focus between controls",
                "  Enter           Activate the focused control",
                "  Esc             Close modal / cancel current overlay",
                "",
                "Global",
                "  Ctrl+K          Open command catalog",
                "  F6              Toggle mouse mode",
                "  Alt+M           Toggle mouse mode",
                "  F7              Previous tab",
                "  F8              Next tab",
                "  Ctrl+R          Refresh",
                "  ?               Show this keymap",
                "  Ctrl+Q          Quit",
                "",
                "Clipboard",
                "  Ctrl+C          Copy",
                "  Ctrl+X          Cut",
                "  Ctrl+V          Paste",
                "  Ctrl+Shift+V    Paste",
                "  Shift+Insert    Paste",
            ]
        )
        dialog_classes = "modal-dialog modal-wide"
        if self.border_style == "ascii":
            dialog_classes += " ascii-border"
        with Vertical(id="keybindings-dialog", classes=dialog_classes):
            yield Static("Keyboard shortcuts", id="keybindings-title", classes="modal-title")
            with PanelScroll(id="keybindings-body-scroll", classes="modal-body-scroll"):
                yield Static(body, id="keybindings-body", classes="modal-body")
            yield ModalButton(
                "Close",
                id="close-keybindings",
                classes="action-button cyan",
            )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-keybindings":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)

    def action_page_up(self) -> None:
        self.query_one("#keybindings-body-scroll", PanelScroll).scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        self.query_one("#keybindings-body-scroll", PanelScroll).scroll_page_down(animate=False)

    def action_item_previous(self) -> None:
        self.query_one("#close-keybindings", Button).focus()

    def action_item_next(self) -> None:
        self.query_one("#close-keybindings", Button).focus()


class ConhostWarningScreen(BorderStyleMixin, ModalScreen[None]):
    """Startup warning for legacy Windows console hosts."""

    CSS = TUI_CSS

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close", show=False),
    ]

    def __init__(self, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.border_style = border_style

    def compose(self) -> ComposeResult:
        dialog_classes = "modal-dialog modal-wide warning"
        if self.border_style == "ascii":
            dialog_classes += " ascii-border"
        body = (
            "Legacy Windows console hosts are not fully supported by the TUI.\n\n"
            "Known limitations include Korean IME input, mouse text selection, and "
            "some clipboard behavior. Windows Terminal is strongly recommended."
        )
        with Vertical(id="conhost-warning-dialog", classes=dialog_classes):
            yield Static(
                "Windows Terminal strongly recommended",
                id="conhost-warning-title",
                classes="modal-title",
            )
            yield Static(body, id="conhost-warning-body", classes="modal-body")
            yield ModalButton(
                "Continue",
                id="close-conhost-warning",
                classes="action-button cyan",
            )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-conhost-warning":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class QuitConfirmScreen(BorderStyleMixin, ModalScreen[bool]):
    """Confirm before quitting the TUI."""

    BUTTON_IDS = ("confirm-quit", "cancel-quit")

    CSS = TUI_CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("left,h,up,k", "focus_yes", "Yes", show=False),
        Binding("right,l,down,j", "focus_no", "No", show=False),
    ]

    def __init__(self, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.border_style = border_style

    def compose(self) -> ComposeResult:
        dialog_classes = "modal-dialog modal-compact warning"
        if self.border_style == "ascii":
            dialog_classes += " ascii-border"
        with Vertical(id="quit-confirm-dialog", classes=dialog_classes):
            yield Static("Quit memtomem?", id="quit-confirm-title", classes="modal-title")
            yield Static(
                "Choose Yes to quit, or No/Esc to return.",
                id="quit-confirm-body",
                classes="modal-body",
            )
            with Horizontal(classes="modal-actions"):
                yield ModalButton("Yes", id="confirm-quit", classes="choice-button")
                yield ModalButton("No", id="cancel-quit", classes="choice-button")

    def on_mount(self) -> None:
        self.focus_quit_button("cancel-quit")

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        widget_id = event.widget.id
        if widget_id in self.BUTTON_IDS:
            self.set_quit_button_styles(widget_id)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-quit":
            self.dismiss(True)
        elif event.button.id == "cancel-quit":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_focus_yes(self) -> None:
        self.focus_quit_button("confirm-quit")

    def action_focus_no(self) -> None:
        self.focus_quit_button("cancel-quit")

    def focus_quit_button(self, button_id: str) -> None:
        self.set_quit_button_styles(button_id)
        self.query_one(f"#{button_id}", Button).focus()

    def set_quit_button_styles(self, active_button_id: str) -> None:
        for button_id in self.BUTTON_IDS:
            button = self.query_one(f"#{button_id}", Button)
            button.set_class(button_id == active_button_id, "cyan")


class TuiInput(Input):
    """Input widget that uses the OS clipboard when possible."""

    BINDINGS = [
        *Input.BINDINGS,
        Binding("ctrl+shift+v,shift+insert", "paste", "Paste text", show=False),
    ]

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            escape = getattr(self.app, "action_escape", None)
            if escape is not None:
                escape()
            return
        if event.key == "ctrl+q":
            event.stop()
            event.prevent_default()
            request_quit = getattr(self.app, "action_request_quit", None)
            if request_quit is not None:
                request_quit()
            return
        if event.key in {"f6", "alt+m"}:
            event.stop()
            event.prevent_default()
            toggle = getattr(self.app, "action_toggle_mouse_mode", None)
            if toggle is not None:
                toggle()
            return
        if event.key in {"f2", "f3", "f4"}:
            event.stop()
            event.prevent_default()
            action_name = {
                "f2": "action_focus_menu",
                "f3": "action_focus_main",
                "f4": "action_focus_detail",
            }[event.key]
            action = getattr(self.app, action_name, None)
            if action is not None:
                action()
            return
        if event.key == "f7":
            event.stop()
            event.prevent_default()
            sync_input_panel = getattr(self.app, "sync_input_panel_for_tab_key", None)
            if sync_input_panel is not None:
                sync_input_panel(self)
            previous_tab = getattr(self.app, "action_tab_previous", None)
            if previous_tab is not None:
                previous_tab()
            return
        if event.key == "f8":
            event.stop()
            event.prevent_default()
            sync_input_panel = getattr(self.app, "sync_input_panel_for_tab_key", None)
            if sync_input_panel is not None:
                sync_input_panel(self)
            next_tab = getattr(self.app, "action_tab_next", None)
            if next_tab is not None:
                next_tab()
            return
        await super()._on_key(event)

    def action_copy(self) -> None:
        selected_text = self.selected_text
        if not selected_text:
            raise SkipAction()
        self.app.copy_to_clipboard(selected_text)
        write_os_clipboard(selected_text)

    def action_cut(self) -> None:
        selected_text = self.selected_text
        if not selected_text:
            raise SkipAction()
        self.app.copy_to_clipboard(selected_text)
        write_os_clipboard(selected_text)
        self.delete_selection()

    def action_paste(self) -> None:
        clipboard = read_os_clipboard()
        if clipboard is None:
            clipboard = self.app.clipboard
        start, end = self.selection
        self.replace(clipboard.splitlines()[0] if clipboard else "", start, end)


class FolderTree(DirectoryTree):
    """Directory tree that hides files for folder-selection workflows."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [path for path in paths if path.is_dir()]


class FolderBrowserScreen(BorderStyleMixin, ModalScreen[Path | None]):
    """Keyboard- and mouse-accessible experimental folder picker."""

    CSS = TUI_CSS
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, path: str | Path, *, border_style: BorderStyle = "solid") -> None:
        super().__init__()
        self.border_style = border_style
        self.selected_path = self.existing_directory(path)

    @staticmethod
    def existing_directory(path: str | Path) -> Path:
        candidate = Path(path).expanduser().resolve()
        while not candidate.is_dir() and candidate != candidate.parent:
            candidate = candidate.parent
        return candidate if candidate.is_dir() else Path.home().resolve()

    def compose(self) -> ComposeResult:
        dialog_classes = "modal-dialog folder-browser-dialog"
        if self.border_style == "ascii":
            dialog_classes += " ascii-border"
        with Vertical(classes=dialog_classes):
            yield Static("Select memory directory", classes="modal-title")
            yield Static(
                "Choose an existing folder. This test browser does not create or modify folders.",
                classes="muted folder-browser-help",
            )
            with Horizontal(classes="folder-browser-location-row"):
                yield Input(
                    value=str(self.selected_path),
                    id="folder-browser-location",
                    classes="text-input",
                )
                yield ModalButton("Go", id="folder-browser-go", classes="action-button cyan")
                yield ModalButton("Up", id="folder-browser-up", classes="action-button")
            yield FolderTree(
                self.selected_path,
                id="folder-browser-tree",
                classes="folder-browser-tree",
            )
            yield Static("Selected", classes="muted")
            yield Static(
                str(self.selected_path),
                id="folder-browser-selected",
                classes="folder-browser-selected",
            )
            with Horizontal(classes="modal-actions"):
                yield ModalButton(
                    "Use this folder",
                    id="folder-browser-use",
                    classes="action-button cyan",
                )
                yield ModalButton(
                    "Cancel",
                    id="folder-browser-cancel",
                    classes="action-button",
                )

    def on_mount(self) -> None:
        self.query_one("#folder-browser-tree", FolderTree).focus()

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self.set_selected_path(event.path)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "folder-browser-location":
            self.go_to_location()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "folder-browser-go":
            self.go_to_location()
        elif event.button.id == "folder-browser-up":
            self.show_directory(self.selected_path.parent)
        elif event.button.id == "folder-browser-use":
            self.dismiss(self.selected_path)
        elif event.button.id == "folder-browser-cancel":
            self.dismiss(None)

    def go_to_location(self) -> None:
        value = self.query_one("#folder-browser-location", Input).value.strip()
        candidate = Path(value).expanduser().resolve()
        if not candidate.is_dir():
            self.notify("Enter an existing directory.", severity="error")
            return
        self.show_directory(candidate)

    def show_directory(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        self.set_selected_path(resolved)
        self.query_one("#folder-browser-tree", FolderTree).path = resolved

    def set_selected_path(self, path: Path) -> None:
        self.selected_path = path.expanduser().resolve()
        self.query_one("#folder-browser-location", Input).value = str(self.selected_path)
        self.query_one("#folder-browser-selected", Static).update(str(self.selected_path))

    def action_cancel(self) -> None:
        self.dismiss(None)


class DiagnosticInput(TuiInput):
    """Input widget that records the raw key events it receives."""

    async def _on_key(self, event: events.Key) -> None:
        recorder = getattr(self.app, "record_key_event", None)
        if recorder is not None:
            recorder(event, self.value)
        await super()._on_key(event)

    def _on_paste(self, event: events.Paste) -> None:
        recorder = getattr(self.app, "record_paste_event", None)
        if recorder is not None:
            recorder(event, self.value)
        super()._on_paste(event)


class InputDiagnosticsApp(BorderStyleMixin, App[None]):
    """Small Textual app for inspecting terminal input events."""

    CSS = TUI_CSS

    BINDINGS = [
        Binding("escape,ctrl+q", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        border_style: BorderStyle = "solid",
        terminal_profile: str | None = None,
    ) -> None:
        super().__init__()
        self.border_style = border_style
        self.terminal_profile = terminal_profile or detect_terminal_profile()
        self.input_events: list[str] = []

    def compose(self) -> ComposeResult:
        log_classes = "log-panel diagnostic-log"
        if self.border_style == "ascii":
            log_classes += " ascii-border"
        with Vertical(id="diagnostics", classes="diagnostic-screen"):
            yield Static(
                "memtomem TUI Input Diagnostics",
                id="diagnostics-title",
                classes="title diagnostic-title",
            )
            if has_ime_limitations(self.terminal_profile):
                yield Static(
                    "Korean IME input is limited in legacy Windows consoles. "
                    "Use Windows Terminal for Korean text input.",
                    classes="warning",
                )
            yield Static(
                "Type Korean text in the field below. Press Escape or Ctrl+Q to quit.",
                classes="muted",
            )
            yield DiagnosticInput(
                placeholder="Type here...",
                id="diagnostics-input",
                classes="text-input diagnostic-input",
            )
            yield Static("", id="diagnostics-value")
            with PanelScroll(id="diagnostics-log", classes=log_classes):
                yield Static("Waiting for key events...", id="diagnostics-log-text")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#diagnostics-input", DiagnosticInput).focus()

    def record_key_event(self, event: events.Key, value_before: str) -> None:
        self._append_input_event(
            "key",
            [
                f"key={event.key!r}",
                f"character={event.character!r}",
                f"printable={event.is_printable}",
                f"value_before={value_before!r}",
            ],
        )

    def record_paste_event(self, event: events.Paste, value_before: str) -> None:
        self._append_input_event(
            "paste",
            [
                f"text={event.text!r}",
                f"value_before={value_before!r}",
            ],
        )

    def _append_input_event(self, event_type: str, fields: list[str]) -> None:
        self.input_events.append(
            f"{len(self.input_events) + 1:03d} {event_type}: " + "  ".join(fields)
        )
        del self.input_events[:-40]
        self.query_one("#diagnostics-log-text", Static).update("\n".join(self.input_events))
        value = self.query_one("#diagnostics-input", DiagnosticInput).value
        self.query_one("#diagnostics-value", Static).update(f"Current value: {value!r}")


class MemtomemTuiApp(BorderStyleMixin, App[None]):
    """Initial Textual shell for memtomem.

    The app starts with readiness routing:

    * no config -> setup screen
    * configured but empty index with files -> index-required screen
    * ready -> dashboard
    """

    CSS = TUI_CSS

    BINDINGS = [
        Binding("escape", "escape", "Escape", show=False),
        Binding("ctrl+q", "request_quit", "Quit"),
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("ctrl+k", "show_catalog", "Commands"),
        Binding("?", "show_keybindings", "Help"),
        Binding("up,k", "item_previous", "Previous item", show=False),
        Binding("down,j", "item_next", "Next item", show=False),
        Binding("page_up", "page_up", "Page up", show=False),
        Binding("pageup", "page_up", "Page up", show=False),
        Binding("page_down", "page_down", "Page down", show=False),
        Binding("pagedown", "page_down", "Page down", show=False),
        Binding("left,h", "item_left", "Previous item", show=False),
        Binding("right,l", "item_right", "Next item", show=False),
        Binding("f2", "focus_menu", "Menu", show=False),
        Binding("f3", "focus_main", "Main", show=False),
        Binding("f4", "focus_detail", "Details", show=False),
        Binding("f6,alt+m", "toggle_mouse_mode", "Mouse mode", show=False),
        Binding("f7", "tab_previous", "Previous tab", show=False),
        Binding("f8", "tab_next", "Next tab", show=False),
        Binding("enter", "nav_activate", "Open menu", show=False),
    ]

    NAV_BUTTON_IDS = (
        "nav-dashboard",
        "nav-search",
        "nav-index",
        "nav-test",
        "nav-commands",
        "nav-settings",
        "nav-refresh",
        "nav-help",
    )
    PANEL_IDS = ("menu", "main", "detail")

    def __init__(
        self,
        *,
        border_style: BorderStyle = "solid",
        startup_refresh: bool = True,
        terminal_profile: str | None = None,
        mouse_enabled: bool = True,
        paths: TuiPaths | None = None,
    ) -> None:
        super().__init__()
        self._components_cm: AbstractAsyncContextManager[Any] | None = None
        self.comp: Any | None = None
        self.readiness: Readiness | None = None
        self.compact = False
        self.menu_compact = False
        self.startup_refresh = startup_refresh
        self.nav_index = 0
        self.panel_index = 0
        self.border_style = border_style
        self.terminal_profile = terminal_profile or detect_terminal_profile()
        self.mouse_enabled = mouse_enabled
        self.paths = paths or resolve_tui_paths(dev=False)
        self.search_results: list[SearchResult] = []
        self.last_search_query = ""
        self.index_section = "overview"
        self.index_sources_cache: list[SourceRow] | None = None
        self.index_sources_cached_at: datetime | None = None
        self.index_root_rows: list[dict[str, Any]] = []
        self.test_section = "one"
        self.test_browse_path = str(Path.home())
        self.test_detail_section = "alpha"
        self.current_page_id = "dashboard"
        self.ui_state: dict[tuple[str, str, str | None, str], UiWidgetState] = {}
        self.panel_focus_ids: dict[str, str | None] = {
            panel_id: None for panel_id in self.PANEL_IDS
        }
        self.skip_next_main_state_save = False
        self.skip_next_detail_state_save = False
        self.focus_next_main_tabs = False
        self.focus_next_detail_tabs = False
        self.footer_offset = 0
        self.settings_index = 0
        self.settings_editing = False
        self.settings_draft_footer_offset = 0
        self._requested_conhost_viewport: tuple[int, int] | None = None

    def compose(self) -> ComposeResult:
        with Container(id="root", classes="app-shell"):
            with Horizontal(id="topbar", classes="topbar"):
                yield Static("memtomem", id="top-title", classes="app-title")
                if self.paths.is_dev:
                    yield Static(
                        "DEV",
                        id="environment-status",
                        classes="status-item environment-status warning",
                    )
                yield Static("", id="mouse-status", classes="status-item mouse-status")
                yield Static("", id="top-clock", classes="status-item clock-status")
            with Horizontal(id="menu-bar", classes="menu-bar"):
                yield MenuItem("Dashboard", id="nav-dashboard", classes="menu-item")
                yield MenuItem("Search", id="nav-search", classes="menu-item")
                yield MenuItem("Index", id="nav-index", classes="menu-item")
                yield MenuItem("Test", id="nav-test", classes="menu-item")
                yield MenuItem("Commands", id="nav-commands", classes="menu-item")
                yield MenuItem("Settings", id="nav-settings", classes="menu-item")
                yield MenuItem("Refresh", id="nav-refresh", classes="menu-item")
                yield MenuItem("Help", id="nav-help", classes="menu-item")
            with Horizontal(id="layout"):
                with Vertical(
                    id="main",
                    classes=f"section-panel main-section {self.border_class}".strip(),
                ):
                    with PanelScroll(id="main-body", classes="section-body"):
                        yield Static("Loading memtomem state...", id="main-content")
                with Vertical(
                    id="detail",
                    classes=f"section-panel detail-section {self.border_class}".strip(),
                ):
                    with PanelScroll(id="detail-body", classes="section-body"):
                        yield Static("Details", classes="title section-title")
                        yield Static(
                            "Press Ctrl+K to inspect the TUI command catalog.",
                            id="detail-text",
                        )
        yield Footer()
        yield Static("", id="footer-spacer")

    async def on_mount(self) -> None:
        self.update_clock()
        self.update_mouse_status()
        self.set_footer_offset(self.footer_offset)
        self.set_interval(1, self.update_clock)
        if self.terminal_profile == "windows-conhost":
            self.set_interval(0.2, self.correct_conhost_viewport_size)
        if self.startup_refresh and not config_exists(self.paths.config_path):
            self.push_screen(
                InitScreen(paths=self.paths, border_style=self.border_style),
                self._finish_initial_setup,
            )
        elif self.startup_refresh:
            await self.refresh_readiness()
        self.focus_panel(0)
        if has_ime_limitations(self.terminal_profile):
            self.push_screen(ConhostWarningScreen(border_style=self.border_style))

    def _finish_initial_setup(self, result: TuiInitState | None) -> None:
        if result is None:
            self.exit()
            return
        self.run_worker(partial(self._complete_initial_setup, result), group="startup")

    async def _complete_initial_setup(self, state: TuiInitState) -> None:
        try:
            initialize_tui_config(self.paths, state=state)
            await self.refresh_readiness()
        except Exception as exc:
            self.notify(f"Initialization failed: {exc}", severity="error", timeout=8)
            self.push_screen(
                InitScreen(paths=self.paths, border_style=self.border_style),
                self._finish_initial_setup,
            )

    async def on_unmount(self) -> None:
        if self._components_cm is not None:
            await self._components_cm.__aexit__(None, None, None)
            self._components_cm = None
            self.comp = None

    async def on_resize(self, event: events.Resize) -> None:
        compact = event.size.width < 100
        menu_compact = event.size.height < 12
        if compact == self.compact and menu_compact == self.menu_compact:
            return
        self.compact = compact
        self.menu_compact = menu_compact
        self.update_compact_visibility()

    def correct_conhost_viewport_size(self) -> None:
        """Correct Textual when conhost restores only its visible viewport."""
        if self.terminal_profile != "windows-conhost":
            return
        normalize_windows_console_buffer_width()
        viewport = windows_console_viewport_size()
        if viewport is None:
            return
        current = (self.size.width, self.size.height)
        if current == viewport:
            self._requested_conhost_viewport = None
            return
        if self._requested_conhost_viewport == viewport:
            return
        self._requested_conhost_viewport = viewport
        size = Size(*viewport)
        self.post_message(events.Resize(size, size))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        button_panel_id = self.panel_id_for_widget(event.button)
        if button_panel_id != self.PANEL_IDS[self.panel_index]:
            return
        if button_id in self.NAV_BUTTON_IDS:
            self.set_nav_selection(self.NAV_BUTTON_IDS.index(button_id))
        else:
            self.sync_panel_from_widget(event.button)
        await self.handle_button(button_id)

    async def on_click(self, event: events.Click) -> None:
        if self.cancel_settings_edit_from_mouse():
            event.stop()
            return
        widget = event.widget
        if widget is not None:
            self.sync_panel_from_widget(widget)
            self.focus_click_target(widget)
        widget_id = getattr(event.widget, "id", None)
        if widget_id in self.NAV_BUTTON_IDS:
            self.set_nav_selection(self.NAV_BUTTON_IDS.index(widget_id))
            return
        if widget_id == "footer-height-setting":
            self.update_settings_row_state()
            return
        if widget_id in {"select-all-roots", "deselect-all-roots", "toggle-all-roots"}:
            event.stop()
            action = self.query_one(f"#{widget_id}", RootSelectionAction)
            self.sync_panel_from_widget(action)
            action.focus()
            await self.handle_button(widget_id)
            return
        if widget_id in {"footer-height-decrease", "footer-height-increase"}:
            event.stop()
            await self.handle_button(widget_id)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-query":
            await self.run_search_from_input()
        elif event.input.id == "one-time-index-path":
            self.run_worker(self.index_one_time_path, exclusive=True, group="index")
        elif event.input.id == "add-root-path":
            await self.add_memory_dir_from_input()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id == "search-results":
            self.update_search_detail(event.list_view.index)
        elif event.list_view.id == "source-list":
            self.update_source_detail(event.list_view.index)

    def on_selection_list_selection_highlighted(
        self, event: SelectionList.SelectionHighlighted[str]
    ) -> None:
        if event.selection_list.id == "root-list":
            self.update_root_detail(event.selection_index)

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        panel_id = self.panel_id_for_widget(event.widget)
        if panel_id is not None and getattr(event.widget, "id", None):
            self.panel_focus_ids[panel_id] = event.widget.id
            if panel_id == "menu" and event.widget.id in self.NAV_BUTTON_IDS:
                self.nav_index = self.NAV_BUTTON_IDS.index(event.widget.id)
            self.update_panel_focus_styles()
        if self.current_page_id == "settings":
            self.update_settings_row_state()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id or ""
        if event.tabs.id == "index-tabs":
            section = tab_id.removeprefix("index-tab-")
            if section in {"overview", "roots", "one-time", "sources"}:
                if section == self.index_section:
                    return
                self.save_panel_state("main", tab_id_override=f"index-tab-{self.index_section}")
                self.skip_next_main_state_save = True
                self.focus_next_main_tabs = True
                self.render_index(section)
        elif event.tabs.id == "test-tabs":
            section = tab_id.removeprefix("test-tab-")
            if section in {"one", "two", "empty", "browse"}:
                if section == self.test_section:
                    return
                self.save_panel_state("main", tab_id_override=f"test-tab-{self.test_section}")
                self.skip_next_main_state_save = True
                self.focus_next_main_tabs = True
                self.render_test_page(section=section)
        elif event.tabs.id == "test-detail-tabs":
            section = tab_id.removeprefix("test-detail-tab-")
            if section in {"alpha", "beta"}:
                if section == self.test_detail_section:
                    return
                self.save_panel_state(
                    "detail",
                    tab_id_override=f"test-detail-tab-{self.test_detail_section}",
                )
                self.skip_next_detail_state_save = True
                self.focus_next_detail_tabs = True
                self.render_test_detail(section)

    async def handle_button(self, button_id: str) -> None:
        if button_id == "nav-refresh":
            await self.restore_default_detail()
            await self.refresh_readiness()
        elif button_id == "nav-dashboard":
            await self.restore_default_detail()
            self.render_dashboard()
        elif button_id == "nav-search":
            await self.restore_default_detail()
            self.render_search()
        elif button_id == "nav-index":
            await self.restore_default_detail()
            self.render_index()
        elif button_id == "nav-test":
            self.render_test_page()
        elif button_id in {"nav-commands", "open-commands"}:
            await self.restore_default_detail()
            self.render_catalog()
        elif button_id == "nav-settings":
            await self.restore_default_detail()
            self.render_settings()
        elif button_id == "run-search":
            await self.run_search_from_input()
        elif button_id == "run-index":
            self.run_worker(self.index_all_memory_dirs, exclusive=True, group="index")
        elif button_id == "index-overview":
            self.render_index("overview")
        elif button_id == "index-roots":
            self.render_index("roots")
        elif button_id == "index-one-time":
            self.render_index("one-time")
        elif button_id == "index-sources":
            self.render_index("sources")
        elif button_id == "add-root":
            await self.add_memory_dir_from_input()
        elif button_id == "reindex-selected-root":
            self.run_worker(
                partial(self.reindex_selected_root, force=False),
                exclusive=True,
                group="index",
            )
        elif button_id == "force-reindex-selected-root":
            self.run_worker(
                partial(self.reindex_selected_root, force=True),
                exclusive=True,
                group="index",
            )
        elif button_id == "remove-selected-root":
            await self.remove_selected_root(delete_chunks=False)
        elif button_id == "remove-selected-root-delete-chunks":
            await self.remove_selected_root(delete_chunks=True)
        elif button_id == "select-all-roots":
            self.apply_root_selection("all")
        elif button_id == "deselect-all-roots":
            self.apply_root_selection("none")
        elif button_id == "toggle-all-roots":
            self.apply_root_selection("invert")
        elif button_id == "run-one-time-index":
            self.run_worker(self.index_one_time_path, exclusive=True, group="index")
        elif button_id == "load-sources":
            self.run_worker(self.load_index_sources, exclusive=True, group="sources")
        elif button_id == "footer-height-decrease":
            self.adjust_footer_height_from_mouse(-1)
        elif button_id == "footer-height-increase":
            self.adjust_footer_height_from_mouse(1)
        elif button_id == "test-browse-path-button":
            self.run_worker(
                self.browse_test_path,
                exclusive=True,
                group="folder-browser",
            )
        elif button_id == "refresh-after-index" or button_id.startswith(
            "dashboard-refresh-preview-"
        ):
            await self.refresh_readiness()
        elif button_id == "nav-help":
            self.action_show_keybindings()
        elif button_id == "reinit-placeholder":
            self.notify(
                "Re-init flow is reserved for a later policy decision.",
                severity="warning",
            )

    async def action_refresh(self) -> None:
        await self.refresh_readiness()

    def action_escape(self) -> None:
        if self.current_page_id == "settings" and self.settings_editing:
            self.cancel_settings_edit()
            return

        focused = getattr(self, "focused", None)
        panel_id = self.panel_id_for_widget(focused)
        active_panel_id = self.PANEL_IDS[self.panel_index]
        if panel_id is None:
            if active_panel_id in {"main", "detail"}:
                self.focus_panel_by_id("menu")
                return
            self.action_request_quit()
            return

        if isinstance(focused, Input):
            self.panel_index = self.PANEL_IDS.index(panel_id)
            self.set_active_panel(panel_id)
            self.focus_parent_or_panel(focused, panel_id)
            return

        if active_panel_id == "menu":
            self.action_request_quit()
            return

        panel_body = self.panel_scroll_target(active_panel_id)
        if focused is panel_body:
            self.focus_panel_by_id("menu")
            return

        self.focus_parent_or_panel(focused, active_panel_id)

    def action_request_quit(self) -> None:
        self.run_worker(self.confirm_quit, exclusive=True, group="quit")

    async def confirm_quit(self) -> None:
        should_quit = await self.push_screen_wait(QuitConfirmScreen(border_style=self.border_style))
        if should_quit:
            self.exit()

    def action_show_catalog(self) -> None:
        self.render_catalog()

    def action_show_keybindings(self) -> None:
        self.push_screen(KeybindingsScreen(border_style=self.border_style))

    def action_panel_previous(self) -> None:
        self.action_item_left()

    def action_panel_next(self) -> None:
        self.action_item_right()

    def action_focus_menu(self) -> None:
        self.focus_panel_by_id("menu")

    def action_focus_main(self) -> None:
        self.focus_panel_by_id("main")

    def action_focus_detail(self) -> None:
        self.focus_panel_by_id("detail")

    def action_item_left(self) -> None:
        if self.current_page_id == "settings" and self.settings_editing:
            return
        self.focus_panel_item_horizontal(-1)

    def action_item_right(self) -> None:
        if self.current_page_id == "settings" and self.settings_editing:
            return
        self.focus_panel_item_horizontal(1)

    def action_item_previous(self) -> None:
        if self.current_page_id == "settings" and self.panel_index == 1:
            self.move_settings_item(-1)
            return
        self.focus_panel_item(-1)

    def action_item_next(self) -> None:
        if self.current_page_id == "settings" and self.panel_index == 1:
            self.move_settings_item(1)
            return
        self.focus_panel_item(1)

    def action_page_up(self) -> None:
        self.scroll_active_panel_page(-1)

    def action_page_down(self) -> None:
        self.scroll_active_panel_page(1)

    def action_toggle_mouse_mode(self) -> None:
        self.set_mouse_enabled(not self.mouse_enabled)
        mode = "TUI Mouse" if self.mouse_enabled else "OS Mouse"
        self.notify(f"Mouse mode: {mode}")

    def action_tab_previous(self) -> None:
        self.move_active_tabs(-1)

    def action_tab_next(self) -> None:
        self.move_active_tabs(1)

    async def action_nav_activate(self) -> None:
        focused = getattr(self, "focused", None)
        focused_panel_id = self.panel_id_for_widget(focused)
        if focused_panel_id != self.PANEL_IDS[self.panel_index]:
            return
        if self.current_page_id == "settings" and isinstance(focused, SettingRow):
            self.toggle_settings_edit()
            return
        if self.current_page_id == "settings" and isinstance(focused, SettingStep) and focused.id:
            await self.handle_button(focused.id)
            return
        if isinstance(focused, RootSelectionAction) and focused.id:
            await self.handle_button(focused.id)
            return
        if isinstance(focused, Input) and focused.id == "search-query":
            await self.run_search_from_input()
            return
        if isinstance(focused, Input) and focused.id == "one-time-index-path":
            self.run_worker(self.index_one_time_path, exclusive=True, group="index")
            return
        if isinstance(focused, Input) and focused.id == "add-root-path":
            await self.add_memory_dir_from_input()
            return
        if isinstance(focused, Button) and focused.id:
            await self.handle_button(focused.id)
            return
        if isinstance(focused, MenuItem) and focused.id:
            await self.handle_button(focused.id)
            return

    def set_nav_selection(self, index: int) -> None:
        self.nav_index = index % len(self.NAV_BUTTON_IDS)

    def focus_nav_button(self, index: int) -> None:
        bounded_index = max(0, min(len(self.NAV_BUTTON_IDS) - 1, index))
        self.set_nav_selection(bounded_index)
        self.focus_panel_by_id("menu", target_id=self.NAV_BUTTON_IDS[self.nav_index])

    def focus_panel(self, index: int) -> None:
        bounded_index = max(0, min(len(self.PANEL_IDS) - 1, index))
        self.focus_panel_by_id(self.PANEL_IDS[bounded_index])

    def focus_panel_by_id(self, panel_id: str, *, target_id: str | None = None) -> None:
        if panel_id not in self.PANEL_IDS:
            return
        self.panel_index = self.PANEL_IDS.index(panel_id)
        self.set_active_panel(panel_id)
        self.update_compact_visibility()

        if target_id is None:
            target_id = self.panel_focus_ids.get(panel_id)
        target = self.focusable_by_id(panel_id, target_id)
        if target is None:
            focusables = self.panel_focusables(panel_id)
            target = focusables[0] if focusables else self.panel_scroll_target(panel_id)
        if getattr(target, "id", None):
            self.panel_focus_ids[panel_id] = target.id
            if panel_id == "menu" and target.id in self.NAV_BUTTON_IDS:
                self.set_nav_selection(self.NAV_BUTTON_IDS.index(target.id))
        target.focus()
        self.update_panel_focus_styles()

    def focus_panel_item(self, direction: int) -> None:
        focused = getattr(self, "focused", None)

        panel_id = self.PANEL_IDS[self.panel_index]
        if panel_id == "menu":
            if direction > 0:
                self.focus_panel_by_id("main")
            return

        if (
            isinstance(focused, (ListView, SelectionList))
            and self.panel_id_for_widget(focused) == panel_id
        ):
            current_index = getattr(focused, "index", None)
            if isinstance(focused, SelectionList):
                current_index = getattr(focused, "highlighted", None)
            if direction < 0 and (current_index is None or current_index <= 0):
                self.focus_panel_by_id("menu")
                return
            if direction < 0:
                focused.action_cursor_up()
            elif current_index is None or current_index < len(focused.children) - 1:
                focused.action_cursor_down()
            return

        if (
            isinstance(focused, RootSelectionAction)
            and self.panel_id_for_widget(focused) == panel_id
        ):
            focusables = self.panel_focusables(panel_id)
            action_indices = [
                index
                for index, widget in enumerate(focusables)
                if isinstance(widget, RootSelectionAction)
            ]
            if action_indices and direction > 0:
                next_index = min(action_indices[-1] + 1, len(focusables) - 1)
                focusables[next_index].focus()
                return
            if action_indices and direction < 0:
                previous_index = max(action_indices[0] - 1, 0)
                focusables[previous_index].focus()
                return

        if getattr(focused, "id", None) == "add-root-path" and direction < 0:
            actions = list(
                self.query(f"#{panel_id} RootSelectionAction").results(RootSelectionAction)
            )
            if actions:
                actions[0].focus()
                return

        if self.focus_directional_item(panel_id, dx=0, dy=direction):
            return

        if direction < 0:
            self.focus_panel_by_id("menu")

    def focus_panel_item_horizontal(self, direction: int) -> None:
        panel_id = self.PANEL_IDS[self.panel_index]

        if panel_id == "menu":
            next_index = self.nav_index + direction
            if 0 <= next_index < len(self.NAV_BUTTON_IDS):
                self.focus_nav_button(next_index)
            return

        if self.focus_directional_item(panel_id, dx=direction, dy=0):
            return

        if panel_id == "main" and direction > 0:
            self.focus_panel_by_id("detail")
            return
        if panel_id == "detail" and direction < 0:
            self.focus_panel_by_id("main")

    def scroll_active_panel_page(self, direction: int) -> None:
        focused = getattr(self, "focused", None)

        panel_id = self.PANEL_IDS[self.panel_index]
        if isinstance(focused, ListView) and self.panel_id_for_widget(focused) == panel_id:
            self.scroll_list_view_page(focused, direction)
            return
        if isinstance(focused, SelectionList) and self.panel_id_for_widget(focused) == panel_id:
            if direction < 0:
                focused.action_page_up()
            else:
                focused.action_page_down()
            return

        scroll_target = self.panel_scroll_target(panel_id)

        if direction < 0:
            scroll_target.scroll_page_up(animate=False)
        else:
            scroll_target.scroll_page_down(animate=False)

    def move_active_tabs(self, direction: int) -> None:
        tabs = self.active_tabs()
        if tabs is None:
            return
        tab_ids = [tab.id for tab in tabs.query(Tab).results(Tab) if tab.id is not None]
        if not tab_ids:
            return
        try:
            current = tab_ids.index(tabs.active or "")
        except ValueError:
            current = 0
        tabs.active = tab_ids[(current + direction) % len(tab_ids)]
        tabs.focus()

    def active_tabs(self) -> Tabs | None:
        panel_id = self.PANEL_IDS[self.panel_index]
        panel = self.query_one(f"#{self.panel_container_id(panel_id)}")
        try:
            return panel.query(Tabs).first()
        except NoMatches:
            pass
        return None

    def scroll_list_view_page(self, list_view: ListView, direction: int) -> None:
        if not list_view.children:
            return
        current = list_view.index
        if current is None:
            current = 0 if direction > 0 else len(list_view.children) - 1
        page_size = max(1, list_view.content_size.height - 1)
        next_index = min(
            max(current + (page_size * direction), 0),
            len(list_view.children) - 1,
        )
        list_view.index = next_index
        list_view.scroll_to_widget(list_view.children[next_index], animate=False)

    def panel_focusables(self, panel_id: str) -> list[Any]:
        return list(
            self.query(
                f"#{self.panel_container_id(panel_id)} Input, "
                f"#{self.panel_container_id(panel_id)} Button, "
                f"#{self.panel_container_id(panel_id)} MenuItem, "
                f"#{self.panel_container_id(panel_id)} ListView, "
                f"#{self.panel_container_id(panel_id)} SelectionList, "
                f"#{self.panel_container_id(panel_id)} Tabs, "
                f"#{self.panel_container_id(panel_id)} SettingRow, "
                f"#{self.panel_container_id(panel_id)} SettingStep, "
                f"#{self.panel_container_id(panel_id)} RootSelectionAction"
            )
        )

    def panel_scroll_target(self, panel_id: str) -> PanelScroll:
        body_id = {
            "main": "main-body",
            "detail": "detail-body",
        }[panel_id]
        return self.query_one(f"#{body_id}", PanelScroll)

    def panel_container_id(self, panel_id: str) -> str:
        return "menu-bar" if panel_id == "menu" else panel_id

    def focusable_by_id(self, panel_id: str, widget_id: str | None) -> Any | None:
        if widget_id is None:
            return None
        for widget in self.panel_focusables(panel_id):
            if getattr(widget, "id", None) == widget_id:
                return widget
        return None

    def focus_directional_item(self, panel_id: str, *, dx: int, dy: int) -> bool:
        focused = getattr(self, "focused", None)
        if self.panel_id_for_widget(focused) != panel_id:
            self.focus_panel_by_id(panel_id)
            return True

        focusables = self.panel_focusables(panel_id)
        if not focusables:
            return False
        if focused not in focusables:
            focusables[0].focus()
            return True

        focused_region = getattr(focused, "region", None)
        if focused_region is None:
            return self.focus_linear_fallback(focusables, focused, dx=dx, dy=dy)

        focused_center_x = focused_region.x + focused_region.width / 2
        focused_center_y = focused_region.y + focused_region.height / 2
        candidates: list[tuple[float, float, Any]] = []
        for candidate in focusables:
            if candidate is focused:
                continue
            region = getattr(candidate, "region", None)
            if region is None:
                continue
            candidate_center_x = region.x + region.width / 2
            candidate_center_y = region.y + region.height / 2
            delta_x = candidate_center_x - focused_center_x
            delta_y = candidate_center_y - focused_center_y
            if dx < 0 and delta_x >= 0:
                continue
            if dx > 0 and delta_x <= 0:
                continue
            if dy < 0 and delta_y >= 0:
                continue
            if dy > 0 and delta_y <= 0:
                continue
            vertical_overlap = self.range_overlap(
                focused_region.y,
                focused_region.y + focused_region.height,
                region.y,
                region.y + region.height,
            )
            horizontal_overlap = self.range_overlap(
                focused_region.x,
                focused_region.x + focused_region.width,
                region.x,
                region.x + region.width,
            )
            if dx and vertical_overlap <= 0:
                continue
            if dy and horizontal_overlap <= 0:
                continue
            primary = abs(delta_x) if dx else abs(delta_y)
            secondary = abs(delta_y) if dx else abs(delta_x)
            candidates.append((primary, secondary, candidate))

        if not candidates:
            return False
        _, _, target = min(candidates, key=lambda item: (item[0], item[1]))
        target.focus()
        return True

    def range_overlap(self, start_a: float, end_a: float, start_b: float, end_b: float) -> float:
        return min(end_a, end_b) - max(start_a, start_b)

    def focus_linear_fallback(
        self, focusables: list[Any], focused: Any, *, dx: int, dy: int
    ) -> bool:
        try:
            focused_index = focusables.index(focused)
        except ValueError:
            return False
        direction = dx or dy
        next_index = focused_index + direction
        if next_index < 0 or next_index >= len(focusables):
            return False
        focusables[next_index].focus()
        return True

    def update_compact_visibility(self) -> None:
        active_panel_id = self.PANEL_IDS[self.panel_index]
        try:
            menu = self.query_one("#menu-bar")
            layout = self.query_one("#layout")
            expanded_menu = self.compact and active_panel_id == "menu"
            menu.set_class(expanded_menu, "compact-expanded")
            layout.display = not expanded_menu
            menu.display = not self.menu_compact or active_panel_id == "menu"
            self.query_one("#main").display = not self.compact or active_panel_id == "main"
            self.query_one("#detail").display = not self.compact or active_panel_id == "detail"
        except NoMatches:
            return

    def update_panel_focus_styles(self) -> None:
        active_panel_id = self.PANEL_IDS[self.panel_index]
        for panel_id in self.PANEL_IDS:
            remembered_id = self.panel_focus_ids.get(panel_id)
            for widget in self.panel_focusables(panel_id):
                is_remembered = getattr(widget, "id", None) == remembered_id
                widget.set_class(
                    is_remembered and panel_id == active_panel_id,
                    "active-panel-focus",
                )
                widget.set_class(
                    is_remembered and panel_id != active_panel_id,
                    "inactive-panel-focus",
                )

    def focus_parent_or_panel(self, widget: Any | None, panel_id: str) -> None:
        parent = getattr(widget, "parent", None)
        panel_body = self.panel_scroll_target(panel_id)
        if parent is not None and parent is not self.screen:
            self.set_focus(parent)
            if getattr(self, "focused", None) is parent:
                return
        self.set_focus(panel_body)

    def set_mouse_enabled(self, enabled: bool) -> None:
        if enabled == self.mouse_enabled:
            return
        driver = getattr(self, "_driver", None)
        if driver is not None:
            if enabled:
                self._write_mouse_sequence(True)
            else:
                self._write_mouse_sequence(False)
        self.mouse_enabled = enabled
        self.update_mouse_status()

    def _write_mouse_sequence(self, enabled: bool) -> None:
        driver = getattr(self, "_driver", None)
        if driver is None:
            return
        suffix = "h" if enabled else "l"
        for mode in ("1000", "1003", "1015", "1006"):
            driver.write(f"\x1b[?{mode}{suffix}")
        driver.flush()

    def prepare_panel_button_click(self, button: PanelButton) -> bool:
        if self.cancel_settings_edit_from_mouse():
            return False
        self.sync_panel_from_widget(button)
        self.focus_click_target(button)
        return True

    def prepare_menu_item_click(self, item: MenuItem) -> bool:
        if self.cancel_settings_edit_from_mouse():
            return False
        self.sync_panel_from_widget(item)
        self.focus_click_target(item)
        if item.id in self.NAV_BUTTON_IDS:
            self.set_nav_selection(self.NAV_BUTTON_IDS.index(item.id))
        return True

    def cancel_settings_edit_from_mouse(self) -> bool:
        if self.current_page_id != "settings" or not self.settings_editing:
            return False
        self.cancel_settings_edit()
        return True

    def sync_panel_from_widget(self, widget: Any | None) -> None:
        if widget is None:
            return
        for index, panel_id in enumerate(self.PANEL_IDS):
            panel = self.query_one(f"#{self.panel_container_id(panel_id)}")
            if widget is panel or panel in getattr(widget, "ancestors", ()):
                self.panel_index = index
                self.set_active_panel(panel_id)
                self.update_compact_visibility()
                return

    def focus_click_target(self, widget: Any | None) -> None:
        current = widget
        while current is not None:
            if getattr(current, "can_focus", False):
                current.focus()
                return
            current = getattr(current, "parent", None)

    def panel_id_for_widget(self, widget: Any | None) -> str | None:
        if widget is None:
            return None
        for panel_id in self.PANEL_IDS:
            panel = self.query_one(f"#{self.panel_container_id(panel_id)}")
            if widget is panel or panel in getattr(widget, "ancestors", ()):
                return panel_id
        return None

    def sync_input_panel_for_tab_key(self, widget: Any | None) -> None:
        widget_panel_id = self.panel_id_for_widget(widget)
        if widget_panel_id is None:
            return
        active_panel_id = self.PANEL_IDS[self.panel_index]
        if widget_panel_id == active_panel_id or active_panel_id == "menu":
            self.sync_panel_from_widget(widget)

    def set_active_panel(self, panel_id: str) -> None:
        for candidate in self.PANEL_IDS:
            widget = self.query_one(f"#{self.panel_container_id(candidate)}")
            widget.set_class(candidate == panel_id, "active-panel")
        self.update_panel_focus_styles()

    def update_clock(self) -> None:
        try:
            self.query_one("#top-clock", Static).update(datetime.now().strftime("%H:%M:%S"))
        except NoMatches:
            return

    def update_mouse_status(self) -> None:
        try:
            status = "Mouse:TUI" if self.mouse_enabled else "Mouse:OS"
            self.query_one("#mouse-status", Static).update(status)
        except NoMatches:
            return

    def set_footer_offset(self, offset: int) -> None:
        self.footer_offset = max(0, min(3, offset))
        try:
            footer = self.query_one(Footer)
            footer.styles.margin = Spacing(0, 0, self.footer_offset, 0)
        except NoMatches:
            pass
        try:
            self.query_one("#footer-height-value", Static).update(str(self.footer_offset))
        except NoMatches:
            pass
        self.settings_draft_footer_offset = self.footer_offset
        self.update_settings_row_state()

    def move_settings_item(self, direction: int) -> None:
        if self.settings_editing:
            self.settings_draft_footer_offset = max(
                0,
                min(3, self.settings_draft_footer_offset - direction),
            )
            self.update_footer_height_value(self.settings_draft_footer_offset)
            return
        self.settings_index = 0
        self.focus_settings_item()

    def focus_settings_item(self) -> None:
        try:
            self.query_one("#footer-height-setting", SettingRow).focus()
            self.panel_index = 1
            self.set_active_panel("main")
            self.update_settings_row_state()
        except NoMatches:
            pass

    def toggle_settings_edit(self) -> None:
        if self.settings_editing:
            self.set_footer_offset(self.settings_draft_footer_offset)
            self.settings_editing = False
        else:
            self.settings_draft_footer_offset = self.footer_offset
            self.settings_editing = True
            self.update_footer_height_value(self.settings_draft_footer_offset)
        self.update_settings_row_state()

    def cancel_settings_edit(self) -> None:
        self.settings_editing = False
        self.settings_draft_footer_offset = self.footer_offset
        self.update_footer_height_value(self.footer_offset)
        self.update_settings_row_state()

    def adjust_footer_height_from_mouse(self, direction: int) -> None:
        self.settings_editing = False
        self.set_footer_offset(self.footer_offset + direction)

    def update_footer_height_value(self, value: int) -> None:
        try:
            self.query_one("#footer-height-value", Static).update(str(value))
        except NoMatches:
            pass

    def update_settings_row_state(self) -> None:
        try:
            row = self.query_one("#footer-height-setting", SettingRow)
            value = self.query_one("#footer-height-value", Static)
        except NoMatches:
            return
        row.set_class(
            getattr(self, "focused", None) is row and not self.settings_editing, "active-nav"
        )
        row.set_class(self.settings_editing, "editing-setting")
        value.set_class(self.settings_editing, "editing-setting")

    async def refresh_readiness(self) -> None:
        if not config_exists(self.paths.config_path):
            self.readiness = Readiness(
                state=ReadinessState.SETUP_REQUIRED,
                message="memtomem is not configured yet.",
            )
            self.render_setup_required()
            return

        if self.comp is None:
            self._components_cm = tui_components(self.paths)
            self.comp = await self._components_cm.__aenter__()

        self.readiness = await inspect_readiness(self.comp)
        if self.readiness.state == ReadinessState.SETUP_REQUIRED:
            self.render_setup_required()
        elif self.readiness.state == ReadinessState.INDEX_TARGETS_REQUIRED:
            self.render_index_targets_required()
        elif self.readiness.state == ReadinessState.INDEX_REQUIRED:
            self.render_index_required()
        elif self.readiness.state == ReadinessState.ERROR:
            self.render_error()
        else:
            self.render_dashboard()

    def _main_body(self) -> PanelScroll:
        try:
            return self.query_one("#main-body", PanelScroll)
        except NoMatches:
            main = self.query_one("#main")
            was_displayed = bool(main.display)
            main.display = True
            try:
                return self.query_one("#main-body", PanelScroll)
            finally:
                main.display = was_displayed

    def _detail_text(self) -> Static:
        try:
            return self.query_one("#detail-text", Static)
        except NoMatches:
            try:
                detail = self.query_one("#detail")
            except NoMatches:
                return Static("")
            was_displayed = bool(detail.display)
            detail.display = True
            try:
                return self.query_one("#detail-text", Static)
            finally:
                detail.display = was_displayed

    async def _replace_main(self, *widgets: Any, page_id: str | None = None) -> bool:
        if self.skip_next_main_state_save:
            self.skip_next_main_state_save = False
        else:
            self.save_panel_state("main")
        if page_id is not None:
            self.current_page_id = page_id
        try:
            main_panel = self.query_one("#main")
        except NoMatches:
            return False
        was_displayed = bool(main_panel.display)
        main_panel.display = True
        main = self._main_body()
        main.scroll_home(animate=False)
        await main.remove_children()
        for widget in widgets:
            await main.mount(widget)
        main_panel.display = was_displayed
        self.restore_panel_state("main")
        if self.focus_next_main_tabs:
            self.focus_next_main_tabs = False
            self.focus_panel_tabs("main")
        elif self.PANEL_IDS[self.panel_index] == "main":
            self.focus_panel_by_id("main")
        else:
            self.update_panel_focus_styles()
        return False

    async def _replace_detail(self, *widgets: Any) -> bool:
        if self.skip_next_detail_state_save:
            self.skip_next_detail_state_save = False
        else:
            self.save_panel_state("detail")
        detail_panel = self.query_one("#detail")
        was_displayed = bool(detail_panel.display)
        detail_panel.display = True
        detail = self.query_one("#detail-body", PanelScroll)
        detail.scroll_home(animate=False)
        await detail.remove_children()
        for widget in widgets:
            await detail.mount(widget)
        detail_panel.display = was_displayed
        self.restore_panel_state("detail")
        if self.focus_next_detail_tabs:
            self.focus_next_detail_tabs = False
            self.focus_panel_tabs("detail")
        elif self.PANEL_IDS[self.panel_index] == "detail":
            self.focus_panel_by_id("detail")
        else:
            self.update_panel_focus_styles()
        return False

    async def restore_default_detail(self) -> None:
        try:
            self.query_one("#detail-text", Static)
            return
        except NoMatches:
            pass
        await self._replace_detail(
            Static("Details", classes="title"),
            Static("Press Ctrl+K to inspect the TUI command catalog.", id="detail-text"),
        )

    def panel_active_tab_id(self, panel_id: str) -> str | None:
        try:
            panel = self.query_one(f"#{panel_id}")
        except NoMatches:
            return None
        try:
            return panel.query(Tabs).first().active
        except NoMatches:
            return None

    def focus_panel_tabs(self, panel_id: str) -> None:
        try:
            panel = self.query_one(f"#{panel_id}")
            tabs = panel.query(Tabs).first()
        except NoMatches:
            return
        self.set_focus(tabs)

    def panel_state_scope(
        self, panel_id: str, tab_id: str | None = None
    ) -> tuple[str, str, str | None]:
        return (self.current_page_id, panel_id, tab_id)

    def widget_state_key(
        self,
        panel_id: str,
        widget_id: str,
        *,
        tab_id: str | None,
    ) -> tuple[str, str, str | None, str]:
        return (*self.panel_state_scope(panel_id, tab_id), widget_id)

    def save_panel_state(self, panel_id: str, *, tab_id_override: str | None = None) -> None:
        try:
            panel = self.query_one(f"#{panel_id}")
        except NoMatches:
            return

        tab_id = (
            tab_id_override if tab_id_override is not None else self.panel_active_tab_id(panel_id)
        )
        for input_widget in panel.query(Input).results(Input):
            if not input_widget.id:
                continue
            self.ui_state[self.widget_state_key(panel_id, input_widget.id, tab_id=tab_id)] = (
                UiWidgetState(value=input_widget.value)
            )

    def restore_panel_state(self, panel_id: str) -> None:
        try:
            panel = self.query_one(f"#{panel_id}")
        except NoMatches:
            return

        tab_id = self.panel_active_tab_id(panel_id)
        for input_widget in panel.query(Input).results(Input):
            if not input_widget.id:
                continue
            state = self.ui_state.get(
                self.widget_state_key(panel_id, input_widget.id, tab_id=tab_id)
            )
            if state is None:
                continue
            if state.value is not None:
                input_widget.value = state.value

    def render_setup_required(self) -> None:
        self.run_worker(self._render_setup_required, exclusive=True, group="render")

    async def _render_setup_required(self) -> None:
        preset_lines = []
        for name, preset in PRESETS.items():
            marker = " (default)" if name == "english" else ""
            preset_lines.append(f"- {preset.label}{marker}: {preset.description}")
        await self._replace_main(
            Static("Setup required", classes="title"),
            Static(
                f"No {self.paths.config_path} was found. The TUI should route first-time "
                "users into a native init wizard here.",
                classes="warning",
            ),
            Static("Canonical mm init presets:", classes="title"),
            Static("\n".join(preset_lines)),
            Static(
                f"Advanced wizard: {len(ADVANCED_STEPS)} steps. "
                "Re-init policy is intentionally not implemented yet.",
                classes="muted",
            ),
            Static(
                "Implementation note: this screen is the entry point for the upcoming "
                "Textual init wizard. The existing CLI init flow remains unchanged.",
                classes="muted",
            ),
            PanelButton("Re-run init / setup policy placeholder", id="reinit-placeholder"),
            page_id="setup",
        )
        self._detail_text().update("State: SetupRequired\nNext: native init wizard.")

    def render_index_targets_required(self) -> None:
        self.run_worker(self._render_index_targets_required, exclusive=True, group="render")

    async def _render_index_targets_required(self) -> None:
        await self._replace_main(
            Static("Memory directory required", classes="title"),
            Static(
                "Configuration exists, but no memory directories are configured.",
                classes="warning",
            ),
            Static("Add a memory directory before indexing.", classes="muted"),
            PanelButton("Refresh", id="refresh-after-index"),
            page_id="setup",
        )
        self._detail_text().update("State: IndexTargetsRequired")

    def render_index_required(self) -> None:
        self.run_worker(self._render_index_required, exclusive=True, group="render")

    async def _render_index_required(self) -> None:
        assert self.readiness is not None
        dirs = "\n".join(f"- {p}" for p in self.readiness.memory_dirs)
        await self._replace_main(
            Static("Indexing required", classes="title"),
            Static(
                f"{self.readiness.indexable_files} indexable file(s) were found, "
                "but the index is empty.",
                classes="warning",
            ),
            Static(dirs or "(no memory dirs)", classes="muted"),
            PanelButton("Index now", id="run-index", classes="action-button cyan"),
            PanelButton("Refresh", id="refresh-after-index"),
            Static("", id="index-log"),
            page_id="setup",
        )
        self._detail_text().update("State: IndexRequired\nAction: Index configured memory dirs.")

    def render_error(self) -> None:
        self.run_worker(self._render_error, exclusive=True, group="render")

    async def _render_error(self) -> None:
        assert self.readiness is not None
        await self._replace_main(
            Static("Runtime error", classes="title"),
            Static(self.readiness.message, classes="error"),
            Static(self.readiness.error or "Unknown error", classes="muted"),
            PanelButton("Refresh", id="refresh-after-index"),
            page_id="error",
        )
        self._detail_text().update("State: Error")

    def render_dashboard(self) -> None:
        self.run_worker(self._render_dashboard, exclusive=True, group="render")

    async def _render_dashboard(self) -> None:
        if self.readiness is None:
            await self.refresh_readiness()
            return
        await self._replace_main(
            Static("Dashboard", classes="title"),
            Static(self.readiness.message, classes="ok"),
            Static(f"Chunks:  {self.readiness.total_chunks}"),
            Static(f"Sources: {self.readiness.total_sources}"),
            Static(f"Memory dirs: {len(self.readiness.memory_dirs)}", classes="muted"),
            PanelButton("Refresh", id="refresh-after-index"),
            Static("Temporary color CSS preview", classes="muted"),
            PanelButton(
                "Refresh",
                id="dashboard-refresh-preview-panel-blue",
                classes="action-button cyan",
            ),
            PanelButton(
                "Refresh",
                id="dashboard-refresh-preview-primary-blue",
                classes="action-button blue",
            ),
            PanelButton(
                "Refresh",
                id="dashboard-refresh-preview-green",
                classes="action-button green",
            ),
            PanelButton(
                "Refresh",
                id="dashboard-refresh-preview-red",
                classes="action-button red",
            ),
            PanelButton(
                "Refresh",
                id="dashboard-refresh-preview-yellow",
                classes="action-button yellow",
            ),
            PanelButton("Command catalog", id="open-commands"),
            page_id="dashboard",
        )
        self._detail_text().update(
            "Ready for native screens:\n- Search\n- Add memory\n- Recall\n- Tags\n- Config\n"
        )

    def render_search(self) -> None:
        self.run_worker(self._render_search, exclusive=True, group="render")

    async def _render_search(self) -> None:
        query_input = TuiInput(
            value=self.last_search_query,
            placeholder="Search memories...",
            id="search-query",
            classes="text-input search-input",
        )
        widgets: list[Static | Button | Input | ListView] = [Static("Search", classes="title")]
        if has_ime_limitations(self.terminal_profile):
            widgets.append(
                Static(
                    "Korean IME input is limited in legacy Windows consoles. "
                    "Use Windows Terminal for Korean text input.",
                    classes="warning",
                )
            )
        widgets.extend(
            [
                query_input,
                PanelButton("Search", id="run-search", classes="action-button cyan"),
                Static("Enter a query, then press Enter or the Search button.", classes="muted"),
                ListView(id="search-results", classes="data-list result-list"),
            ]
        )
        await self._replace_main(
            *widgets,
            page_id="search",
        )
        self.search_results = []
        self._detail_text().update(
            "Search\n"
            "- Enter: run search from the query field\n"
            "- Up/Down: move through results\n"
            "- PgUp/PgDn: scroll results"
        )

    async def run_search_from_input(self) -> None:
        query = self.query_one("#search-query", Input).value.strip()
        self.last_search_query = query
        if not query:
            self._detail_text().update("Search query cannot be empty.")
            return
        self.run_worker(partial(self._run_search, query), exclusive=True, group="search")

    async def _run_search(self, query: str) -> None:
        results_view = self.query_one("#search-results", ListView)
        await results_view.clear()
        await results_view.append(ListItem(Static("Searching...")))
        self._detail_text().update(f"Searching for: {query}")

        if self.comp is None:
            await self.refresh_readiness()
        if self.comp is None:
            self._detail_text().update("Search unavailable: memtomem runtime is not initialized.")
            return

        from memtomem.server.tools.search import (
            _resolve_project_context_root as _resolve_project_context_root_from_cwd,
        )

        project_context_root = _resolve_project_context_root_from_cwd(self.comp)
        results, stats = await self.comp.search_pipeline.search(
            query,
            top_k=10,
            source_filter=None,
            tag_filter=None,
            namespace=None,
            scope=None,
            project_context_root=project_context_root,
        )
        self.search_results = list(results)
        await results_view.clear()
        if not self.search_results:
            await results_view.append(ListItem(Static("No results.")))
            self._detail_text().update(
                f"No results for: {query}\n"
                f"BM25: {stats.bm25_candidates}  Dense: {stats.dense_candidates}"
            )
            return

        for result in self.search_results:
            await results_view.append(ListItem(Static(self.search_result_label(result))))
        results_view.index = 0
        self.update_search_detail(0, stats)

    def search_result_label(self, result: SearchResult) -> str:
        metadata = result.chunk.metadata
        source = str(metadata.source_file)
        label = " > ".join(metadata.heading_hierarchy) if metadata.heading_hierarchy else source
        snippet = " ".join(result.chunk.content.strip().split())[:64]
        return f"{result.rank:>2}. {result.score:.3f}  {label}  {snippet}"

    def update_search_detail(self, index: int | None, stats: Any | None = None) -> None:
        if index is None or index < 0 or index >= len(self.search_results):
            return
        result = self.search_results[index]
        metadata = result.chunk.metadata
        heading = " > ".join(metadata.heading_hierarchy) if metadata.heading_hierarchy else "(none)"
        tags = ", ".join(metadata.tags) if metadata.tags else "(none)"
        stats_line = ""
        if stats is not None:
            stats_line = (
                f"\n\nPipeline: {stats.bm25_candidates} BM25 + "
                f"{stats.dense_candidates} dense -> {stats.final_total} final"
            )
        self._detail_text().update(
            f"Rank: {result.rank}\n"
            f"Score: {result.score:.4f}\n"
            f"Source: {metadata.source_file}\n"
            f"Namespace: {metadata.namespace or '(default)'}\n"
            f"Heading: {heading}\n"
            f"Tags: {tags}\n\n"
            f"{result.chunk.content.strip()[:1600]}"
            f"{stats_line}"
        )

    def render_catalog(self) -> None:
        items = []
        for entry in COMMAND_CATALOG:
            label = f"{entry.command:<24} {entry.support.value:<9} {entry.title}"
            items.append(ListItem(Static(label)))
        list_view = ListView(
            *items,
            classes="data-list remaining-space-list command-list",
        )
        self.run_worker(
            partial(
                self._replace_main,
                Static("TUI command catalog", classes="title"),
                Static(
                    "Tracks how existing mm commands will be surfaced in the TUI.",
                    classes="muted",
                ),
                list_view,
                page_id="commands",
            ),
            exclusive=True,
            group="render",
        )
        self._detail_text().update("Catalog statuses: native, palette, planned, dangerous.")

    def render_settings(self) -> None:
        self.run_worker(self._render_settings, exclusive=True, group="render")

    async def _render_settings(self) -> None:
        await self._replace_main(
            Static("Settings", classes="title"),
            Static(
                "Select a setting with Up/Down, press Enter to edit, Enter to apply, "
                "or Esc to cancel.",
                classes="muted",
            ),
            Vertical(
                Horizontal(
                    SettingRow(
                        "Footer height",
                        id="footer-height-setting",
                        classes="setting-row",
                    ),
                    SettingStep(
                        "v",
                        id="footer-height-decrease",
                        classes="compact-control setting-step",
                    ),
                    Static(
                        str(self.footer_offset),
                        id="footer-height-value",
                        classes="setting-value",
                    ),
                    SettingStep(
                        "^",
                        id="footer-height-increase",
                        classes="compact-control setting-step",
                    ),
                    id="footer-height-row",
                    classes="setting-row-layout",
                ),
                id="settings-list",
                classes="settings-list",
            ),
            page_id="settings",
        )
        self.settings_editing = False
        self.settings_draft_footer_offset = self.footer_offset
        self.update_settings_row_state()
        self._detail_text().update(
            "Footer height reserves blank lines below the footer. "
            "It is a runtime display adjustment and is not persisted yet."
        )

    # Temporary tab/focus test page. Remove nav-test and this block after manual verification.
    def render_test_page(self, section: str | None = None) -> None:
        if section is not None:
            self.test_section = section
        self.run_worker(self._render_test_page, exclusive=True, group="render")

    async def _render_test_page(self) -> None:
        widgets: list[Any] = [
            Static("Test", classes="title"),
            self.test_tabs(),
        ]
        if self.test_section == "one":
            widgets.extend(
                [
                    Static("One input tab", classes="muted"),
                    TuiInput(
                        placeholder="Test input one...",
                        id="test-input-one",
                        classes="text-input",
                    ),
                ]
            )
        elif self.test_section == "two":
            widgets.extend(
                [
                    Static("Two inputs tab", classes="muted"),
                    TuiInput(
                        placeholder="Test input two A...",
                        id="test-input-two-a",
                        classes="text-input",
                    ),
                    TuiInput(
                        placeholder="Test input two B...",
                        id="test-input-two-b",
                        classes="text-input",
                    ),
                ]
            )
        elif self.test_section == "browse":
            widgets.extend(
                [
                    Static("Folder browser prototype", classes="muted"),
                    Horizontal(
                        TuiInput(
                            value=self.test_browse_path,
                            placeholder="Path to a memory directory...",
                            id="test-browse-path",
                            classes="text-input",
                        ),
                        PanelButton(
                            "Browse...",
                            id="test-browse-path-button",
                            classes="action-button cyan",
                        ),
                        classes="path-picker-row",
                    ),
                    Static(
                        "Type a path directly or open the TUI folder browser.",
                        classes="muted",
                    ),
                ]
            )
        else:
            widgets.extend(
                [
                    Static("No input tab", classes="muted"),
                    Static("This tab intentionally has no input boxes."),
                    ListView(
                        ListItem(Static("List row 1")),
                        ListItem(Static("List row 2")),
                        ListItem(Static("List row 3")),
                        id="test-list",
                        classes="data-list",
                    ),
                ]
            )
        await self._replace_main(*widgets, page_id="test")
        await self._render_test_detail()

    def test_tabs(self) -> Tabs:
        return Tabs(
            Tab("One input", id="test-tab-one"),
            Tab("Two inputs", id="test-tab-two"),
            Tab("No input", id="test-tab-empty"),
            Tab("Browse", id="test-tab-browse"),
            active=f"test-tab-{self.test_section}",
            id="test-tabs",
            classes="tab-bar",
        )

    async def browse_test_path(self) -> None:
        path_input = self.query_one("#test-browse-path", Input)
        result = await self.push_screen_wait(
            FolderBrowserScreen(path_input.value, border_style=self.border_style)
        )
        if result is None:
            return
        self.test_browse_path = str(result)
        path_input.value = self.test_browse_path

    def render_test_detail(self, section: str | None = None) -> None:
        if section is not None:
            self.test_detail_section = section
        self.run_worker(self._render_test_detail, exclusive=True, group="render")

    async def _render_test_detail(self) -> None:
        content = (
            "Details tab alpha.\nMove focus to this panel, then press F7/F8 to verify detail tabs."
            if self.test_detail_section == "alpha"
            else "Details tab beta.\nThis panel has its own independent tab group."
        )
        await self._replace_detail(
            Static("Details", classes="title"),
            self.test_detail_tabs(),
            Static(content, id="test-detail-content"),
        )

    def test_detail_tabs(self) -> Tabs:
        return Tabs(
            Tab("Alpha", id="test-detail-tab-alpha"),
            Tab("Beta", id="test-detail-tab-beta"),
            active=f"test-detail-tab-{self.test_detail_section}",
            id="test-detail-tabs",
            classes="tab-bar",
        )

    def render_index(self, section: str | None = None) -> None:
        if section is not None:
            self.index_section = section
        self.run_worker(self._render_index, exclusive=True, group="render")

    async def _render_index(self) -> None:
        if self.index_section == "overview":
            await self._render_index_overview()
        elif self.index_section == "roots":
            await self._render_index_roots()
        elif self.index_section == "one-time":
            await self._render_index_one_time()
        else:
            await self._render_index_sources()

    def index_tabs(self) -> Tabs:
        return Tabs(
            Tab("Overview", id="index-tab-overview"),
            Tab("Managed roots", id="index-tab-roots"),
            Tab("One-time index", id="index-tab-one-time"),
            Tab("Indexed sources", id="index-tab-sources"),
            active=f"index-tab-{self.index_section}",
            id="index-tabs",
            classes="tab-bar index-tabs",
        )

    async def _render_index_overview(self) -> None:
        stats = {"total_chunks": 0, "total_sources": 0}
        dense_line = "Dense vectors: unavailable"
        orphan_line = "Orphan sources: unavailable"
        if self.comp is None:
            await self.refresh_readiness()
        if self.comp is not None:
            stats = await self.comp.storage.get_stats()
            if hasattr(self.comp.storage, "get_dense_coverage"):
                cov = await self.comp.storage.get_dense_coverage()
                total = int(cov["total"])
                with_dense = int(cov["with_dense"])
                pct = round((with_dense / total) * 100, 1) if total else 0.0
                dense_line = f"Dense vectors: {with_dense}/{total} ({pct}%)"
            try:
                source_files = await self.comp.storage.get_all_source_files()
                orphaned = sum(1 for source in source_files if not source.exists())
                orphan_line = f"Orphan sources: {orphaned}"
            except Exception:
                orphan_line = "Orphan sources: unavailable"
        await self._replace_main(
            Static("Index", classes="title"),
            self.index_tabs(),
            Static("Index stats", classes="title"),
            Static(f"Total chunks:  {stats.get('total_chunks', 0)}"),
            Static(f"Source files:  {stats.get('total_sources', 0)}"),
            Static(dense_line),
            Static(orphan_line, classes="muted"),
            page_id="index",
        )
        self._detail_text().update(
            "Dense vectors show how many indexed chunks have semantic-search embeddings.\n"
            "Below 100% means keyword search may still work, but dense search may miss "
            "some chunks. BM25-only mode can make this expected."
        )

    async def _render_index_roots(self) -> None:
        self.index_root_rows = []
        if self.comp is None:
            await self.refresh_readiness()
        if self.comp is not None:
            from memtomem.indexing.engine import memory_dir_stats

            self.index_root_rows = await memory_dir_stats(
                self.comp.storage,
                self.comp.config.indexing.all_index_roots(),
                supported_extensions=self.comp.config.indexing.supported_extensions,
            )
        items = [
            (
                (
                    f"{idx + 1:>2}. {row['path']}  "
                    f"sources={row['source_file_count']} chunks={row['chunk_count']} "
                    f"exists={row['exists']}"
                ),
                str(Path(row["path"]).expanduser().resolve()),
            )
            for idx, row in enumerate(self.index_root_rows)
        ]
        list_view = ManagedRootsSelectionList(
            *items,
            id="root-list",
            classes="data-list selection-list managed-roots-list",
        )
        add_input = TuiInput(
            placeholder="Path to add to memory_dirs...",
            id="add-root-path",
            classes="text-input",
        )
        await self._replace_main(
            Static("Managed roots", classes="title"),
            self.index_tabs(),
            Static(
                "These paths are registered index roots and watcher targets. "
                "Use Space to select one or more roots.",
                classes="muted",
            ),
            list_view,
            Horizontal(
                RootSelectionAction(
                    "*", id="select-all-roots", classes="compact-control selection-action"
                ),
                RootSelectionAction(
                    "-", id="deselect-all-roots", classes="compact-control selection-action"
                ),
                RootSelectionAction(
                    "~", id="toggle-all-roots", classes="compact-control selection-action"
                ),
                id="root-selection-toolbar",
                classes="compact-toolbar",
            ),
            add_input,
            PanelButton("Add root", id="add-root", classes="action-button cyan"),
            PanelButton(
                "Reindex selected",
                id="reindex-selected-root",
                classes="action-button cyan",
            ),
            PanelButton(
                "Force reindex selected",
                id="force-reindex-selected-root",
                classes="action-button cyan",
            ),
            PanelButton(
                "Remove selected",
                id="remove-selected-root",
                classes="action-button cyan",
            ),
            PanelButton(
                "Remove selected + delete chunks",
                id="remove-selected-root-delete-chunks",
                classes="action-button cyan",
            ),
            Static("", id="index-log", classes="log-panel index-log"),
            page_id="index",
        )
        self._detail_text().update(
            "Managed roots are stored in indexing.memory_dirs/project_memory_dirs and are watched "
            "by the background file watcher when the server or web app is running.\n\n"
            "Selection controls: * selects all roots, - clears the selection, ~ inverts it."
        )
        if items:
            list_view.highlighted = 0

    async def _render_index_one_time(self) -> None:
        path_input = TuiInput(
            placeholder="Path to index once...",
            id="one-time-index-path",
            classes="text-input",
        )
        await self._replace_main(
            Static("One-time index", classes="title"),
            self.index_tabs(),
            Static(
                "Runs the same indexing flow as mm index <path>. "
                "This does not add the path to memory_dirs.",
                classes="muted",
            ),
            path_input,
            PanelButton(
                "Index now",
                id="run-one-time-index",
                classes="action-button cyan",
            ),
            Static("", id="index-log", classes="log-panel index-log"),
            page_id="index",
        )
        self._detail_text().update(
            "One-time indexing writes chunks for the selected path, but it does not make the "
            "path a watcher target. Use Managed roots when the path should stay managed."
        )

    async def _render_index_sources(self) -> None:
        load_label = "Refresh sources" if self.index_sources_cache is not None else "Load sources"
        widgets: list[Any] = [
            Static("Indexed sources", classes="title"),
            self.index_tabs(),
        ]
        if self.index_sources_cache is None:
            widgets.extend(
                [
                    Static("Source list is not loaded yet.", classes="muted"),
                    PanelButton(
                        load_label,
                        id="load-sources",
                        classes="action-button cyan",
                    ),
                    ListView(id="source-list", classes="data-list source-list"),
                ]
            )
        else:
            cached_at = (
                self.index_sources_cached_at.strftime("%H:%M:%S")
                if self.index_sources_cached_at
                else "unknown"
            )
            items = [
                ListItem(
                    Static(
                        f"{idx + 1:>3}. {row.path}  chunks={row.chunks} "
                        f"updated={row.last_updated or '-'}"
                    )
                )
                for idx, row in enumerate(self.index_sources_cache)
            ]
            widgets.extend(
                [
                    Static(
                        f"Cached {len(self.index_sources_cache)} source(s) at {cached_at}.",
                        classes="muted",
                    ),
                    PanelButton(
                        load_label,
                        id="load-sources",
                        classes="action-button cyan",
                    ),
                    ListView(*items, id="source-list", classes="data-list source-list"),
                ]
            )
        await self._replace_main(*widgets, page_id="index")
        try:
            source_list = self.query_one("#source-list", ListView)
            if source_list.children:
                source_list.index = 0
        except NoMatches:
            pass
        self._detail_text().update(
            "Indexed sources are grouped from DB chunks by source_file. "
            "The list loads on demand and is cached until Refresh sources is pressed."
        )

    async def add_memory_dir_from_input(self) -> None:
        if self.comp is None:
            await self.refresh_readiness()
        if self.comp is None:
            return
        path = self.query_one("#add-root-path", Input).value.strip()
        if not path:
            self._detail_text().update("Enter a path to add.")
            return
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            resolved.mkdir(parents=True, exist_ok=True)
        current = [Path(p).expanduser().resolve() for p in self.comp.config.indexing.memory_dirs]
        if resolved not in current:
            self.comp.config.indexing.memory_dirs.append(resolved)
            save_tui_config(self.paths, self.comp.config)
        self.notify(f"Added root: {resolved}")
        self.render_index("roots")

    def selected_root_paths(self) -> list[Path]:
        try:
            selection_list = self.query_one("#root-list", SelectionList)
        except NoMatches:
            return []
        return [Path(path).expanduser().resolve() for path in selection_list.selected]

    def apply_root_selection(self, mode: str) -> None:
        try:
            selection_list = self.query_one("#root-list", SelectionList)
        except NoMatches:
            return
        if mode == "all":
            selection_list.select_all()
        elif mode == "none":
            selection_list.deselect_all()
        elif mode == "invert":
            selection_list.toggle_all()
        self.update_root_detail(selection_list.highlighted or 0)

    async def reindex_selected_root(self, *, force: bool) -> None:
        if self.comp is None:
            await self.refresh_readiness()
        roots = self.selected_root_paths()
        if self.comp is None or not roots:
            self._detail_text().update("Select at least one managed root first.")
            return
        for root in roots:
            await self.run_index_stream(root, recursive=True, force=force, namespace=None)
        await self.refresh_readiness()
        self.render_index("roots")

    async def remove_selected_root(self, *, delete_chunks: bool) -> None:
        if self.comp is None:
            await self.refresh_readiness()
        roots = self.selected_root_paths()
        if self.comp is None or not roots:
            self._detail_text().update("Select at least one managed root first.")
            return
        from memtomem.indexing.engine import norm_dir_prefix
        from memtomem.storage.sqlite_helpers import norm_path

        selected_norms = {norm_path(root) for root in roots}
        current_norms = {
            norm_path(Path(p).expanduser()) for p in self.comp.config.indexing.memory_dirs
        }
        if not selected_norms.issubset(current_norms):
            self._detail_text().update("Only user-tier memory_dirs can be removed here.")
            return
        new_dirs = [
            p
            for p in self.comp.config.indexing.memory_dirs
            if norm_path(Path(p).expanduser()) not in selected_norms
        ]
        if not new_dirs:
            self._detail_text().update("Cannot remove the last memory_dir.")
            return
        deleted_chunks = 0
        self.comp.config.indexing.memory_dirs = new_dirs
        save_tui_config(self.paths, self.comp.config)
        if delete_chunks:
            rows = await self.comp.storage.get_source_files_with_counts()
            prefixes = [norm_dir_prefix(root) for root in roots]
            for row in rows:
                source_path = row[0]
                if any(norm_path(source_path).startswith(prefix) for prefix in prefixes):
                    deleted_chunks += await self.comp.storage.delete_by_source(source_path)
        message = "Removed roots:\n" + "\n".join(f"- {root}" for root in roots)
        if delete_chunks:
            message += f"\nDeleted chunks: {deleted_chunks}"
            self.index_sources_cache = None
        self._detail_text().update(message)
        self.notify("Root removed")
        await self.refresh_readiness()
        self.render_index("roots")

    async def index_one_time_path(self) -> None:
        if self.comp is None:
            await self.refresh_readiness()
        if self.comp is None:
            return
        path = self.query_one("#one-time-index-path", Input).value.strip()
        if not path:
            self._detail_text().update("Enter a path to index.")
            return
        resolved = Path(path).expanduser().resolve()
        await self.run_index_stream(resolved, recursive=True, force=False, namespace=None)
        self.index_sources_cache = None
        self.readiness = await inspect_readiness(self.comp)

    async def load_index_sources(self) -> None:
        if self.comp is None:
            await self.refresh_readiness()
        if self.comp is None:
            return
        self._detail_text().update("Loading indexed sources...")
        rows = await self.comp.storage.get_source_files_with_counts()
        self.index_sources_cache = [
            SourceRow(path=row[0], chunks=int(row[1]), last_updated=row[2], namespaces=row[3])
            for row in rows
        ]
        self.index_sources_cached_at = datetime.now()
        self.render_index("sources")

    def update_root_detail(self, index: int | None) -> None:
        if index is None or index < 0 or index >= len(self.index_root_rows):
            return
        row = self.index_root_rows[index]
        self._detail_text().update(
            f"Path: {row['path']}\n"
            f"Exists: {row['exists']}\n"
            f"Category: {row.get('category')}\n"
            f"Kind: {row.get('kind')}\n"
            f"Indexable files: {row.get('file_count')}\n"
            f"Source files: {row.get('source_file_count')}\n"
            f"Chunks: {row.get('chunk_count')}\n"
            f"Last indexed: {row.get('last_indexed') or '-'}"
        )

    def update_source_detail(self, index: int | None) -> None:
        if self.index_sources_cache is None:
            return
        if index is None or index < 0 or index >= len(self.index_sources_cache):
            return
        row = self.index_sources_cache[index]
        self._detail_text().update(
            f"Source: {row.path}\n"
            f"Exists: {row.path.exists()}\n"
            f"Chunks: {row.chunks}\n"
            f"Namespaces: {row.namespaces or '(default)'}\n"
            f"Last updated: {row.last_updated or '-'}"
        )

    async def index_all_memory_dirs(self) -> None:
        if self.comp is None or self.readiness is None:
            await self.refresh_readiness()
            return

        for root in self.readiness.memory_dirs:
            resolved = Path(root).expanduser().resolve()
            await self.run_index_stream(resolved, recursive=True, force=False, namespace=None)
        await self.refresh_readiness()

    async def run_index_stream(
        self,
        path: Path,
        *,
        recursive: bool,
        force: bool,
        namespace: str | None,
    ) -> None:
        if self.comp is None:
            return
        log = self.query_one("#index-log", Static)
        log.update(f"Starting indexing...\nPath: {path}")
        total_files = 0
        done_files = 0
        indexed = 0
        skipped = 0
        deleted = 0
        errors: list[str] = []
        async for event in self.comp.index_engine.index_path_stream(
            path,
            recursive=recursive,
            force=force,
            namespace=namespace,
        ):
            event_type = event.get("type")
            if event_type == "discovery":
                total_files = int(event.get("files_total", 0))
                log.update(f"Indexing...\nPath: {path}\nFiles discovered: {total_files}")
            elif event_type == "progress":
                done_files = int(event.get("files_done", done_files))
                indexed += int(event.get("indexed", 0))
                skipped += int(event.get("skipped", 0))
                current = event.get("file", str(path))
                log.update(
                    f"Indexing...\n"
                    f"Path: {path}\n"
                    f"Files: {done_files}/{total_files}\n"
                    f"Indexed: {indexed}  Skipped: {skipped}  Deleted: {deleted}\n"
                    f"Current: {current}"
                )
            elif event_type == "complete":
                indexed = int(event.get("indexed_chunks", indexed))
                skipped = int(event.get("skipped_chunks", skipped))
                deleted = int(event.get("deleted_chunks", deleted))
                errors.extend(str(err) for err in event.get("errors", []))
        summary = (
            "Indexing complete.\n"
            f"Files: {total_files}\n"
            f"Indexed: {indexed}  Skipped: {skipped}  Deleted: {deleted}"
        )
        if errors:
            summary += "\nErrors:\n" + "\n".join(f"- {err}" for err in errors[:8])
        log.update(summary)


def run(
    *,
    border_style: BorderStyle = "solid",
    mouse: bool = True,
    terminal_profile: str | None = None,
    paths: TuiPaths | None = None,
) -> None:
    """Run the Textual app."""

    MemtomemTuiApp(
        border_style=border_style,
        terminal_profile=terminal_profile,
        mouse_enabled=mouse,
        paths=paths,
    ).run(mouse=mouse)


def run_input_diagnostics(
    *,
    border_style: BorderStyle = "solid",
    mouse: bool = True,
    terminal_profile: str | None = None,
) -> None:
    """Run the Textual input diagnostics app."""

    InputDiagnosticsApp(border_style=border_style, terminal_profile=terminal_profile).run(
        mouse=mouse
    )
