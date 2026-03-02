import asyncio
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType, MessageEntityType
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, InputMediaPhoto, Message
from dotenv import load_dotenv
import yt_dlp

URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
TIKTOK_SHORT_DOMAINS = {"vm.tiktok.com", "vt.tiktok.com"}
YOUTUBE_DOMAINS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


@dataclass
class ExternalVideoDownload:
    source_url: str
    path: Path
    title: Optional[str] = None


@dataclass
class ExternalVideoStream:
    source_url: str
    video_url: str
    title: Optional[str] = None


@dataclass
class DownloadResult:
    kind: str  # "video" | "images"
    source_url: str
    title: Optional[str] = None
    video_url: Optional[str] = None
    extra_video_urls: List[str] = field(default_factory=list)
    image_urls: List[str] = field(default_factory=list)


class TikTokDownloader:
    """Loads no-watermark TikTok media via TikWM API."""

    API_URL = "https://www.tikwm.com/api/"

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def resolve_redirect(self, url: str) -> str:
        try:
            async with self.session.get(
                url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=8),
                headers={"User-Agent": USER_AGENT},
            ) as response:
                return str(response.url)
        except Exception:
            return url

    @staticmethod
    def should_resolve_redirect(url: str) -> bool:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().split(":")[0]
        path = parsed.path.lower()
        return domain in TIKTOK_SHORT_DOMAINS or path.startswith("/t/")

    async def fetch(self, url: str) -> DownloadResult:
        original = url.strip()
        candidates = [original]
        if self.should_resolve_redirect(original):
            resolved = await self.resolve_redirect(original)
            candidates = unique_preserve_order([original, resolved])

        errors: List[str] = []
        for candidate in candidates:
            try:
                return await self._fetch_by_url(api_url=candidate, source_url=original)
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
                logging.warning("TikWM candidate failed: %s | %s", candidate, exc)

        raise RuntimeError(
            "TikTok download failed: " + "; ".join(errors if errors else ["unknown error"])
        )

    async def _fetch_by_url(self, api_url: str, source_url: str) -> DownloadResult:
        payload = {"url": api_url, "hd": "1"}
        headers = {"User-Agent": USER_AGENT, "Referer": "https://www.tikwm.com/"}

        async with self.session.post(
            self.API_URL,
            data=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"TikWM HTTP {response.status}")
            body = await response.json(content_type=None)

        code = body.get("code")
        if code not in (0, "0", None):
            msg = body.get("msg") or f"TikWM API code {code}"
            raise RuntimeError(msg)

        data = body.get("data") or {}
        if not data:
            raise RuntimeError("TikWM returned empty data")

        images = self._extract_images(data)
        if images:
            return DownloadResult(
                kind="images",
                source_url=source_url,
                title=data.get("title"),
                image_urls=images,
            )

        # Prefer "play" first because some "hdplay" URLs return 403 more often.
        video_candidates = unique_preserve_order(
            url
            for url in [
                self._normalize_media_url(data.get("play")),
                self._normalize_media_url(data.get("hdplay")),
            ]
            if url
        )
        if not video_candidates:
            raise RuntimeError("No downloadable media found")

        return DownloadResult(
            kind="video",
            source_url=source_url,
            title=data.get("title"),
            video_url=video_candidates[0],
            extra_video_urls=video_candidates[1:],
        )

    def _extract_images(self, data: dict) -> List[str]:
        raw_images = data.get("images")
        if not isinstance(raw_images, list):
            return []

        normalized: List[str] = []
        for item in raw_images:
            if isinstance(item, str):
                url = self._normalize_media_url(item)
                if url:
                    normalized.append(url)
            elif isinstance(item, dict):
                url = self._normalize_media_url(item.get("url"))
                if url:
                    normalized.append(url)

        return normalized

    @staticmethod
    def _normalize_media_url(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        candidate = url.strip()
        if candidate.startswith("//"):
            return f"https:{candidate}"
        return candidate


class MediaStorage:
    def __init__(self, session: aiohttp.ClientSession, directory: Path, max_bytes: int):
        self.session = session
        self.directory = directory
        self.max_bytes = max_bytes
        self.directory.mkdir(parents=True, exist_ok=True)

    async def download(self, url: str, suffix: str) -> Path:
        filename = f"{uuid.uuid4().hex}{suffix}"
        path = self.directory / filename

        referers = ["https://www.tikwm.com/", "https://www.tiktok.com/", ""]
        base_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        last_error: Optional[Exception] = None

        for attempt in range(1, 4):
            for referer in referers:
                headers = dict(base_headers)
                if referer:
                    headers["Referer"] = referer
                try:
                    async with self.session.get(
                        url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=45),
                    ) as response:
                        if response.status != 200:
                            raise RuntimeError(f"Media HTTP {response.status}")
                        if response.content_length and response.content_length > self.max_bytes:
                            raise RuntimeError("File is larger than MAX_FILE_MB")

                        total = 0
                        with path.open("wb") as output:
                            async for chunk in response.content.iter_chunked(256 * 1024):
                                total += len(chunk)
                                if total > self.max_bytes:
                                    raise RuntimeError("File is larger than MAX_FILE_MB")
                                output.write(chunk)
                    return path
                except Exception as exc:
                    last_error = exc
                    try:
                        if path.exists():
                            path.unlink()
                    except OSError:
                        logging.warning("Could not remove incomplete file: %s", path)
            if attempt < 3:
                await asyncio.sleep(0.6 * attempt)

        if last_error:
            raise last_error
        raise RuntimeError("Media download failed")


class YtDlpSilentLogger:
    def debug(self, msg: str) -> None:
        logging.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        logging.debug("yt-dlp warning: %s", msg)

    def error(self, msg: str) -> None:
        logging.debug("yt-dlp error: %s", msg)


class YtDlpDownloader:
    """Downloads video files for platforms supported by yt-dlp."""

    def __init__(self, directory: Path, max_bytes: int):
        self.directory = directory
        self.max_bytes = max_bytes
        self.directory.mkdir(parents=True, exist_ok=True)

    async def extract_video_stream(self, url: str) -> ExternalVideoStream:
        return await asyncio.to_thread(self._extract_video_stream_sync, url)

    async def download_video(self, url: str) -> ExternalVideoDownload:
        return await asyncio.to_thread(self._download_video_sync, url)

    def _base_ydl_options(self) -> dict:
        options = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": YtDlpSilentLogger(),
            "noplaylist": True,
            "retries": 5,
            "fragment_retries": 5,
            "extractor_retries": 3,
            "concurrent_fragment_downloads": 4,
            "socket_timeout": 30,
            "http_headers": {"User-Agent": USER_AGENT},
            "format": (
                "best[height<=720][ext=mp4][vcodec!=none][acodec!=none]/"
                "best[ext=mp4][vcodec!=none][acodec!=none]/"
                "best[vcodec!=none][acodec!=none]/best"
            ),
        }
        cookie_file = os.getenv("YT_DLP_COOKIE_FILE")
        if cookie_file:
            options["cookiefile"] = cookie_file
        return options

    def _extract_video_stream_sync(self, url: str) -> ExternalVideoStream:
        ydl_options = self._base_ydl_options()
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(url, download=False)

        video_url = self._resolve_stream_url(info)
        if not video_url:
            raise RuntimeError("No direct media URL found")

        return ExternalVideoStream(
            source_url=url,
            video_url=video_url,
            title=(info or {}).get("title"),
        )

    def _download_video_sync(self, url: str) -> ExternalVideoDownload:
        download_id = uuid.uuid4().hex
        output_template = str(self.directory / f"{download_id}.%(ext)s")

        ydl_options = self._base_ydl_options()
        ydl_options.update(
            {
                "outtmpl": output_template,
                "overwrites": True,
                "restrictfilenames": True,
            }
        )

        info: dict = {}
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(url, download=True)
            path = self._resolve_downloaded_path(ydl, info, download_id)

        if not path.exists():
            raise RuntimeError("Downloaded file not found")

        size_bytes = path.stat().st_size
        if size_bytes > self.max_bytes:
            path.unlink(missing_ok=True)
            raise RuntimeError("File is larger than MAX_FILE_MB")

        return ExternalVideoDownload(
            source_url=url,
            path=path,
            title=(info or {}).get("title"),
        )

    @staticmethod
    def _resolve_stream_url(info: dict) -> Optional[str]:
        if not isinstance(info, dict):
            return None

        # Most progressive formats expose a single direct URL.
        direct = info.get("url")
        if isinstance(direct, str) and direct.startswith("http"):
            return direct

        requested = info.get("requested_downloads")
        if isinstance(requested, list):
            for item in requested:
                candidate = item.get("url")
                if isinstance(candidate, str) and candidate.startswith("http"):
                    return candidate

        formats = info.get("formats")
        if isinstance(formats, list):
            for item in reversed(formats):
                if not isinstance(item, dict):
                    continue
                if item.get("vcodec") in (None, "none"):
                    continue
                if item.get("acodec") in (None, "none"):
                    continue
                candidate = item.get("url")
                if isinstance(candidate, str) and candidate.startswith("http"):
                    return candidate

        return None

    def _resolve_downloaded_path(
        self, ydl: yt_dlp.YoutubeDL, info: dict, download_id: str
    ) -> Path:
        requested = info.get("requested_downloads")
        if isinstance(requested, list):
            for item in requested:
                filepath = item.get("filepath") or item.get("_filename")
                if filepath:
                    candidate = Path(filepath)
                    if candidate.exists():
                        return candidate

        prepared = Path(ydl.prepare_filename(info))
        if prepared.exists():
            return prepared

        matches = sorted(self.directory.glob(f"{download_id}.*"))
        if matches:
            return max(matches, key=lambda file: file.stat().st_size)

        return prepared


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def extract_urls(message: Message) -> List[str]:
    urls: List[str] = []

    text_parts = [part for part in [message.text, message.caption] if part]
    for part in text_parts:
        urls.extend(URL_RE.findall(part))

    entity_groups = [
        (message.text, message.entities),
        (message.caption, message.caption_entities),
    ]
    for source, entities in entity_groups:
        if not source or not entities:
            continue
        for entity in entities:
            if entity.type == MessageEntityType.TEXT_LINK and entity.url:
                urls.append(entity.url)
            elif entity.type == MessageEntityType.URL:
                urls.append(source[entity.offset : entity.offset + entity.length])

    return unique_preserve_order(u.rstrip(".,!?:;)") for u in urls)


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def is_tiktok_url(url: str) -> bool:
    domain = get_domain(url)
    return bool(domain) and (domain.endswith("tiktok.com") or domain in TIKTOK_SHORT_DOMAINS)


def is_instagram_reel_url(url: str) -> bool:
    domain = get_domain(url)
    if not domain.endswith("instagram.com"):
        return False
    path = urlparse(url).path.lower()
    return path.startswith("/reel/") or path.startswith("/reels/")


def is_youtube_shorts_url(url: str) -> bool:
    domain = get_domain(url)
    if domain not in YOUTUBE_DOMAINS:
        return False
    path = urlparse(url).path.lower()
    if domain == "youtu.be":
        return True
    return path.startswith("/shorts/")


def detect_platform(url: str) -> Optional[str]:
    if is_tiktok_url(url):
        return "tiktok"
    if is_instagram_reel_url(url):
        return "instagram_reel"
    if is_youtube_shorts_url(url):
        return "youtube_shorts"
    return None


def extension_from_url(url: str, fallback: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".mp4"):
        if path.endswith(ext):
            return ext
    return fallback


def cleanup_files(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            logging.warning("Could not remove temp file: %s", path)


def build_caption(result: DownloadResult) -> str:
    max_caption_len = 1024
    source_line = f"Источник: {result.source_url}"
    if not result.title:
        return source_line[:max_caption_len]

    title = result.title.strip()
    separator = "\n\n"
    max_title_len = max_caption_len - len(separator) - len(source_line)
    if max_title_len <= 0:
        return source_line[:max_caption_len]
    if len(title) > max_title_len:
        if max_title_len > 3:
            title = title[: max_title_len - 3] + "..."
        else:
            title = title[:max_title_len]
    return f"{title}{separator}{source_line}"


def get_video_candidate_urls(result: DownloadResult) -> List[str]:
    return unique_preserve_order(
        url for url in [result.video_url, *result.extra_video_urls] if url
    )


async def send_video_result(
    message: Message,
    result: DownloadResult,
    caption: str,
    storage: MediaStorage,
    files_to_cleanup: List[Path],
) -> Message:
    candidates = get_video_candidate_urls(result)
    if not candidates:
        raise RuntimeError("No video URL candidates found")

    errors: List[str] = []

    # Fast path: ask Telegram to fetch media directly by URL.
    for video_url in candidates:
        try:
            return await message.answer_video(
                video=video_url,
                caption=caption,
                supports_streaming=True,
            )
        except Exception as exc:
            errors.append(f"direct: {exc}")
            logging.warning("Direct video send failed: %s | %s", video_url, exc)

    # Fallback: download locally and upload from disk.
    for video_url in candidates:
        try:
            video_path = await storage.download(
                video_url,
                extension_from_url(video_url, ".mp4"),
            )
            files_to_cleanup.append(video_path)
            return await message.answer_video(
                video=FSInputFile(video_path),
                caption=caption,
                supports_streaming=True,
            )
        except Exception as exc:
            errors.append(str(exc))
            logging.warning("Video fallback download failed: %s | %s", video_url, exc)

    raise RuntimeError("Video send failed: " + "; ".join(errors[-3:]))


async def send_images_result(
    message: Message,
    result: DownloadResult,
    caption: str,
    storage: MediaStorage,
    files_to_cleanup: List[Path],
    download_concurrency: int,
) -> List[Message]:
    image_urls = result.image_urls[:30]
    if not image_urls:
        raise RuntimeError("TikTok image list is empty")

    # Fast path: direct URL send.
    try:
        if len(image_urls) == 1:
            sent = await message.answer_photo(photo=image_urls[0], caption=caption)
            return [sent]

        sent_messages: List[Message] = []
        for index in range(0, len(image_urls), 10):
            chunk = image_urls[index : index + 10]
            media = [
                InputMediaPhoto(
                    media=image_url,
                    caption=caption if index == 0 and idx == 0 else None,
                )
                for idx, image_url in enumerate(chunk)
            ]
            sent_messages.extend(await message.answer_media_group(media=media))
        return sent_messages
    except Exception as exc:
        logging.warning("Direct image send failed, using local fallback: %s", exc)

    # Fallback: download locally and upload from disk.
    semaphore = asyncio.Semaphore(max(1, download_concurrency))

    async def download_one(index: int, image_url: str) -> Tuple[int, Optional[Path]]:
        async with semaphore:
            try:
                image_path = await storage.download(
                    image_url,
                    extension_from_url(image_url, ".jpg"),
                )
                return index, image_path
            except Exception as exc:
                logging.warning("Image download failed: %s | %s", image_url, exc)
                return index, None

    results = await asyncio.gather(
        *(download_one(index, image_url) for index, image_url in enumerate(image_urls))
    )
    image_paths = [path for _, path in sorted(results, key=lambda item: item[0]) if path]
    files_to_cleanup.extend(image_paths)

    if not image_paths:
        raise RuntimeError("All image URLs failed to download")

    if len(image_paths) == 1:
        sent = await message.answer_photo(photo=FSInputFile(image_paths[0]), caption=caption)
        return [sent]

    sent_messages: List[Message] = []
    for index in range(0, len(image_paths), 10):
        chunk = image_paths[index : index + 10]
        media = [
            InputMediaPhoto(
                media=FSInputFile(path),
                caption=caption if index == 0 and idx == 0 else None,
            )
            for idx, path in enumerate(chunk)
        ]
        sent_messages.extend(await message.answer_media_group(media=media))
    return sent_messages


async def send_external_video_result(
    message: Message,
    source_url: str,
    external_downloader: YtDlpDownloader,
    files_to_cleanup: List[Path],
) -> Message:
    direct_error: Optional[Exception] = None

    # Fast path: extract direct stream and let Telegram fetch it.
    try:
        stream = await external_downloader.extract_video_stream(source_url)
        caption = build_caption(
            DownloadResult(
                kind="video",
                source_url=stream.source_url,
                title=stream.title,
            )
        )
        return await message.answer_video(
            video=stream.video_url,
            caption=caption,
            supports_streaming=True,
        )
    except Exception as exc:
        direct_error = exc
        logging.warning("Direct external video send failed for %s: %s", source_url, exc)

    # Fallback: local download and upload.
    downloaded = await external_downloader.download_video(source_url)
    files_to_cleanup.append(downloaded.path)
    caption = build_caption(
        DownloadResult(
            kind="video",
            source_url=downloaded.source_url,
            title=downloaded.title,
        )
    )
    try:
        return await message.answer_video(
            video=FSInputFile(downloaded.path),
            caption=caption,
            supports_streaming=True,
        )
    except Exception as fallback_exc:
        if direct_error:
            raise RuntimeError(
                f"Direct send failed: {direct_error}; fallback upload failed: {fallback_exc}"
            ) from fallback_exc
        raise


async def main() -> None:
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    max_file_mb = int(os.getenv("MAX_FILE_MB", "50"))
    project_dir = Path(__file__).resolve().parent
    download_dir = project_dir / "downloads"
    image_download_concurrency = max(1, int(os.getenv("IMAGE_DOWNLOAD_CONCURRENCY", "6")))
    link_process_concurrency = max(1, int(os.getenv("LINK_PROCESS_CONCURRENCY", "2")))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    session = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
    )
    bot = Bot(token=token)
    dp = Dispatcher()

    downloader = TikTokDownloader(session)
    storage = MediaStorage(session, download_dir, max_file_mb * 1024 * 1024)
    external_downloader = YtDlpDownloader(download_dir, max_file_mb * 1024 * 1024)

    @dp.message(CommandStart())
    async def start_handler(message: Message) -> None:
        await message.answer(
            "Бот активен. Добавьте в группу и отключите Privacy Mode в BotFather, "
            "чтобы бот видел все сообщения и автоматически обрабатывал ссылки на "
            "TikTok, Instagram Reels и YouTube Shorts."
        )

    @dp.message(Command("status"))
    async def status_handler(message: Message) -> None:
        await message.answer(
            "Бот запущен.\n"
            f"MAX_FILE_MB={max_file_mb}\n"
            f"DOWNLOAD_DIR={download_dir}\n"
            f"IMAGE_DOWNLOAD_CONCURRENCY={image_download_concurrency}\n"
            f"LINK_PROCESS_CONCURRENCY={link_process_concurrency}\n"
            "Поддержка: TikTok / Instagram Reels / YouTube Shorts.\n"
            "Отправка медиа: сначала напрямую по URL, локальное скачивание только как fallback.\n"
            "Медиа после отправки остаются в Telegram и удаляются только локально с ПК.\n"
            "Если бот не видит ссылки в группе: отключите Group Privacy в BotFather."
        )

    @dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP, ChatType.PRIVATE}))
    async def chat_handler(message: Message) -> None:
        if not message.from_user or message.from_user.is_bot:
            return

        links_with_platform: List[Tuple[str, str]] = []
        for url in extract_urls(message):
            platform = detect_platform(url)
            if platform:
                links_with_platform.append((url, platform))

        if not links_with_platform:
            return

        async def process_link(link: str, platform: str) -> None:
            files_to_cleanup: List[Path] = []
            try:
                if platform == "tiktok":
                    result = await downloader.fetch(link)
                    caption = build_caption(result)

                    if result.kind == "video":
                        await send_video_result(
                            message=message,
                            result=result,
                            caption=caption,
                            storage=storage,
                            files_to_cleanup=files_to_cleanup,
                        )
                        return

                    await send_images_result(
                        message=message,
                        result=result,
                        caption=caption,
                        storage=storage,
                        files_to_cleanup=files_to_cleanup,
                        download_concurrency=image_download_concurrency,
                    )
                    return

                await send_external_video_result(
                    message=message,
                    source_url=link,
                    external_downloader=external_downloader,
                    files_to_cleanup=files_to_cleanup,
                )

            except Exception as exc:
                logging.exception("Failed to process %s link: %s", platform, link)
                reason = str(exc).strip() or "unknown error"
                if platform == "instagram_reel" and "cookie" in reason.lower():
                    reason = (
                        "Instagram ограничил доступ к ролику. "
                        "Добавьте YT_DLP_COOKIE_FILE в .env с cookies вашего браузера."
                    )
                if len(reason) > 180:
                    reason = reason[:177] + "..."
                await message.reply(
                    "Не удалось обработать ссылку. "
                    f"Причина: {reason}"
                )
            finally:
                cleanup_files(files_to_cleanup)

        if len(links_with_platform) == 1:
            link, platform = links_with_platform[0]
            await process_link(link, platform)
            return

        semaphore = asyncio.Semaphore(link_process_concurrency)

        async def process_link_with_limit(link: str, platform: str) -> None:
            async with semaphore:
                await process_link(link, platform)

        await asyncio.gather(
            *(process_link_with_limit(link, platform) for link, platform in links_with_platform)
        )

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
