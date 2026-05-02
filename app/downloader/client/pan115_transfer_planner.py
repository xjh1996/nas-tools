import os
import re

from config import DEFAULT_MOVIE_FORMAT, DEFAULT_TV_FORMAT, RMT_MEDIAEXT, RMT_MIN_FILESIZE


class Pan115TransferPlanner:
    """
    Build dry-run transfer plans for 115 remote media files.

    This is deliberately lighter than FileTransfer: it does not identify media
    through TMDB yet. The caller provides media metadata, and the planner reuses
    nas-tools naming templates to compute remote target paths.
    """

    def __init__(self, remote_fs, config=None):
        self.remote_fs = remote_fs
        self.config = dict(config or {})
        self.err = None
        media_config = dict(self.config.get("media") or {})
        self.movie_name_format = media_config.get("movie_name_format") or DEFAULT_MOVIE_FORMAT
        self.tv_name_format = media_config.get("tv_name_format") or DEFAULT_TV_FORMAT
        self.min_filesize = self._resolve_min_filesize(media_config.get("min_filesize"))

    def plan(self, source_path, media_info, library_root, execute=False, overwrite=False):
        source_path = self.remote_fs.normalize_path(source_path)
        library_root = self.remote_fs.normalize_path(library_root)
        media_info = self._normalize_media_info(media_info)
        if not media_info.get("title"):
            self.err = "media title is required"
            return False, []
        if not library_root:
            self.err = "library_root is required"
            return False, []

        ret, source = self.remote_fs.stat(source_path)
        if not ret:
            self.err = self.remote_fs.err
            return False, []

        source_items = [source]
        if source.get("is_dir"):
            ret, source_items = self.remote_fs.walk(source_path)
            if not ret:
                self.err = self.remote_fs.err
                return False, []
            source_items = [item for item in source_items if self._is_transferable_media_file(item)]
            if not source_items:
                self.err = "no media files found under remote path: %s" % source_path
                return False, []
        else:
            source_items = [item for item in source_items if self._is_transferable_media_file(item)]
            if not source_items:
                self.err = "remote path is not a supported media file: %s" % source_path
                return False, []

        plans = []
        for item in source_items:
            target_path = self.build_target_path(item, media_info, library_root)
            ok, plan = self.remote_fs.move_path(
                item.get("path"),
                target_path,
                execute=execute,
                overwrite=overwrite
            )
            plan["ok"] = ok
            plan["media_info"] = media_info
            plans.append(plan)
            if not ok:
                self.err = self.remote_fs.err or plan.get("error")
                if execute or plan.get("target_exists"):
                    return False, plans
        self.err = None
        return True, plans

    def build_target_path(self, source_item, media_info, library_root):
        media_info = self._normalize_media_info(media_info)
        ext = os.path.splitext(source_item.get("name") or "")[-1]
        format_dict = self._format_dict(media_info, source_item)
        if media_info.get("type") in ["tv", "anime"]:
            dir_name, season_name, file_name = self._format_tv_path(format_dict)
            return self.remote_fs.join(library_root, dir_name, season_name, "%s%s" % (file_name, ext))
        dir_name, file_name = self._format_movie_path(format_dict)
        return self.remote_fs.join(library_root, dir_name, "%s%s" % (file_name, ext))

    def _format_movie_path(self, format_dict):
        movie_formats = self.movie_name_format.rsplit("/", 1)
        dir_format = movie_formats[0] if movie_formats else "{title} ({year})"
        file_format = movie_formats[-1] if len(movie_formats) > 1 else "{title} ({year})"
        return self._clean_format(dir_format, format_dict), self._clean_format(file_format, format_dict)

    def _format_tv_path(self, format_dict):
        tv_formats = self.tv_name_format.rsplit("/", 2)
        dir_format = tv_formats[0] if tv_formats else "{title} ({year})"
        season_format = tv_formats[-2] if len(tv_formats) > 2 else "Season {season}"
        file_format = tv_formats[-1] if len(tv_formats) > 2 else "{title} - {season_episode}"
        return (
            self._clean_format(dir_format, format_dict),
            self._clean_format(season_format, format_dict),
            self._clean_format(file_format, format_dict)
        )

    def _format_dict(self, media_info, source_item):
        original_name = os.path.splitext(source_item.get("name") or "")[0]
        season = self._pad_int(media_info.get("season"), 2)
        episode = self._pad_int(media_info.get("episode"), 2)
        season_episode = ""
        if season and episode:
            season_episode = "S%sE%s" % (season, episode)
        return {
            "title": media_info.get("title"),
            "en_title": media_info.get("en_title"),
            "original_title": media_info.get("original_title"),
            "original_name": media_info.get("original_name") or original_name,
            "name": media_info.get("name") or media_info.get("title"),
            "year": media_info.get("year"),
            "edition": media_info.get("edition"),
            "videoFormat": media_info.get("videoFormat") or media_info.get("video_format"),
            "releaseGroup": media_info.get("releaseGroup") or media_info.get("release_group"),
            "effect": media_info.get("effect"),
            "videoCodec": media_info.get("videoCodec") or media_info.get("video_codec"),
            "audioCodec": media_info.get("audioCodec") or media_info.get("audio_codec"),
            "tmdbid": media_info.get("tmdbid"),
            "season": season,
            "episode": episode,
            "episode_title": media_info.get("episode_title"),
            "season_episode": season_episode,
            "part": media_info.get("part")
        }

    @staticmethod
    def _clean_format(format_string, format_dict):
        class SafeDict(dict):
            def __missing__(self, key):
                return None

        value = format_string.format_map(SafeDict(format_dict))
        value = re.sub(r"[-_\s.]*None", "", value)
        value = re.sub(r"\s+", " ", value)
        value = value.replace(" /", "/").replace("/ ", "/").strip(" .-_")
        return value or "Unknown"

    @staticmethod
    def _normalize_media_info(media_info):
        media_info = dict(media_info or {})
        media_info["type"] = str(media_info.get("type") or media_info.get("media_type") or "movie").lower()
        return media_info

    @staticmethod
    def _is_media_file(item):
        if not item or not item.get("is_file"):
            return False
        return os.path.splitext(item.get("name") or "")[-1].lower() in RMT_MEDIAEXT

    def _is_transferable_media_file(self, item):
        if not self._is_media_file(item):
            return False
        return int(item.get("size") or 0) >= int(self.min_filesize or 0)

    @staticmethod
    def _pad_int(value, width):
        if value is None or value == "":
            return None
        try:
            return str(int(value)).zfill(width)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _resolve_min_filesize(value):
        if isinstance(value, int):
            return value * 1024 * 1024
        if isinstance(value, str) and value.isdigit():
            return int(value) * 1024 * 1024
        return RMT_MIN_FILESIZE
