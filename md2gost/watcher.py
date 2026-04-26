from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from .converter import ConversionError, ConvertOptions, convert
from .validator import ValidationError, print_warnings, validate


class _MDFileHandler(FileSystemEventHandler):
    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        template: Path | None,
        options: ConvertOptions,
        no_validate: bool = False,
    ) -> None:
        self._input = input_path.resolve()
        self._output = output_path
        self._template = template
        self._options = options
        self._no_validate = no_validate

    def on_modified(self, event: FileSystemEvent) -> None:
        if Path(str(event.src_path)).resolve() == self._input:
            self._run()

    def _run(self) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{ts}] Изменён {self._input.name}")
        try:
            if not self._no_validate:
                warnings = validate(self._input)
                print_warnings(warnings)
            _, elapsed = convert(self._input, self._output, self._template, self._options)
            print(f"           ✓ {self._output.name} готов ({elapsed:.1f}s)")
        except ValidationError as exc:
            print(f"           ✗ Ошибка валидации: {exc}")
        except ConversionError as exc:
            print(f"           ✗ Ошибка конвертации:\n{exc}")


def watch(
    input_path: str | Path,
    output_path: str | Path | None = None,
    template: str | Path | None = None,
    options: ConvertOptions | None = None,
    no_validate: bool = False,
) -> None:
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_suffix(".docx")
    output_path = Path(output_path)
    if template is not None:
        template = Path(template)
    if options is None:
        options = ConvertOptions()

    handler = _MDFileHandler(input_path, output_path, template, options, no_validate)

    print(f"Слежу за {input_path.name}... (Ctrl+C для остановки)")

    # первый запуск сразу при старте
    handler._run()

    observer = Observer()
    observer.schedule(handler, str(input_path.parent), recursive=False)
    observer.start()

    try:
        while observer.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        print("\nОстановлено.")
