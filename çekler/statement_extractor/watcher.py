from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock, Timer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from statement_extractor.src.excel_writer import calculate_weighted_average_maturity
from statement_extractor.src.pdf_reader import PdfReadError
from statement_extractor.src.service import create_excel_from_parse_result, extract_checks_from_pdf
from statement_extractor.src.utils import format_try_amount, safe_filename


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = PACKAGE_DIR / "input"
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "outputs"
DEFAULT_LOG_DIR = PACKAGE_DIR / "logs"
DEBOUNCE_SECONDS = 2.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Input klasörünü izleyip PDF'ten otomatik çek Excel raporu üretir.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="İzlenecek PDF klasörü")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Excel raporlarının yazılacağı klasör")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Log dosyalarının yazılacağı klasör")
    parser.add_argument("--today", help="Vade hesapları için referans tarih. Örnek: 2026-05-03")
    parser.add_argument(
        "--include-overdue-in-value-calc",
        action="store_true",
        help="Vadesi geçmiş çekleri Değer Hesabı ağırlıklı ortalama vade hesabına dahil et",
    )
    parser.add_argument("--process-existing", action="store_true", help="Başlangıçta input klasöründeki mevcut PDF'leri işle")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    log_dir = Path(args.log_dir)
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else None

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = WatchLogger(log_dir)
    processor = PdfReportProcessor(
        output_dir=output_dir,
        logger=logger,
        today=today,
        include_overdue_in_value_calc=args.include_overdue_in_value_calc,
    )

    if args.process_existing:
        for pdf_path in sorted(input_dir.glob("*.pdf")):
            if should_process_path(pdf_path):
                processor.process(pdf_path)

    handler = PdfWatchHandler(processor)
    observer = Observer()
    observer.schedule(handler, str(input_dir), recursive=False)
    observer.start()
    logger.log(f"Watcher başlatıldı. Input: {input_dir} Output: {output_dir}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.log("Watcher durduruluyor.")
        observer.stop()
    observer.join()
    return 0


class PdfWatchHandler(FileSystemEventHandler):
    def __init__(self, processor: "PdfReportProcessor") -> None:
        self.processor = processor
        self._timers: dict[Path, Timer] = {}
        self._lock = Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        self._schedule(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._schedule(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        dest_path = getattr(event, "dest_path", None)
        if dest_path:
            self._schedule_path(Path(dest_path))

    def _schedule(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._schedule_path(Path(event.src_path))

    def _schedule_path(self, path: Path) -> None:
        if not should_process_path(path):
            return
        with self._lock:
            old_timer = self._timers.pop(path, None)
            if old_timer:
                old_timer.cancel()
            timer = Timer(DEBOUNCE_SECONDS, self._run, args=(path,))
            self._timers[path] = timer
            timer.start()

    def _run(self, path: Path) -> None:
        with self._lock:
            self._timers.pop(path, None)
        self.processor.process(path)


class PdfReportProcessor:
    def __init__(
        self,
        output_dir: Path,
        logger: "WatchLogger",
        today: date | None = None,
        include_overdue_in_value_calc: bool = False,
    ) -> None:
        self.output_dir = output_dir
        self.logger = logger
        self.today = today
        self.include_overdue_in_value_calc = include_overdue_in_value_calc

    def process(self, pdf_path: Path) -> None:
        try:
            wait_until_file_is_stable(pdf_path)
            self.logger.log(f"PDF algılandı: {pdf_path.name}")

            parse_result = extract_checks_from_pdf(pdf_path, today=self.today)
            if parse_result.summary.total_count == 0:
                self.logger.log("ALINAN ÇEK kaydı bulunamadı. Excel üretilmedi.")
                return

            average_maturity = calculate_weighted_average_maturity(
                parse_result.checks,
                today=self.today,
                include_overdue=self.include_overdue_in_value_calc,
            )
            output_path = self.output_dir / build_report_filename(pdf_path)
            create_excel_from_parse_result(
                parse_result,
                output_path,
                today=self.today,
                include_debug=True,
                include_overdue_in_value_calc=self.include_overdue_in_value_calc,
            )

            self.logger.log(f"{parse_result.summary.total_count} çek bulundu.")
            self.logger.log(f"Toplam çek tutarı: {format_try_amount(parse_result.summary.total_amount)}")
            self.logger.log(f"Ağırlıklı ortalama vade: {format_decimal(average_maturity)} gün")
            self.logger.log(f"Excel oluşturuldu: {output_path}")
        except PdfReadError as exc:
            self.logger.log(f"PDF okunamadı: {pdf_path.name} - {exc}")
        except Exception as exc:  # pragma: no cover - watcher must stay alive for unknown file/runtime issues
            self.logger.log(f"Hata oluştu: {pdf_path.name} - {exc}")


class WatchLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"watcher_{datetime.now().strftime('%Y-%m-%d')}.log"
        self._lock = Lock()

    def log(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        with self._lock:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a", encoding="utf-8") as file:
                file.write(line + "\n")
        print(line, flush=True)


def should_process_path(path: Path) -> bool:
    name = path.name
    if name == ".DS_Store" or name.startswith(".") or name.startswith("~$"):
        return False
    if name.endswith((".tmp", ".part", ".crdownload")):
        return False
    return path.suffix.lower() == ".pdf"


def build_report_filename(pdf_path: Path) -> str:
    base = safe_filename(pdf_path.stem, default="cek_raporu")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"cek_raporu_{base}_{timestamp}.xlsx"


def wait_until_file_is_stable(path: Path, checks: int = 3, delay: float = 0.7) -> None:
    previous_size = -1
    stable_count = 0
    while stable_count < checks:
        current_size = path.stat().st_size
        if current_size == previous_size:
            stable_count += 1
        else:
            stable_count = 0
            previous_size = current_size
        time.sleep(delay)


def format_decimal(value: Decimal) -> str:
    return f"{value:.2f}".replace(".", ",")


if __name__ == "__main__":
    raise SystemExit(main())
