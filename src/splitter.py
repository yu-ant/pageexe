"""사진 폴더를 지정한 용량 이하의 하위 폴더로 나누는 핵심 로직 (GUI와 분리)."""

import os
import shutil
from dataclasses import dataclass, field

GB = 1024 ** 3
MB = 1024 ** 2

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".heic", ".heif", ".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng",
    ".orf", ".rw2", ".raf", ".srw", ".pef",
}


@dataclass
class FileItem:
    path: str
    size: int
    mtime: float


@dataclass
class Group:
    files: list = field(default_factory=list)
    total: int = 0


def scan_folder(folder, include_all=False):
    """폴더 바로 아래의 사진 파일 목록을 반환한다 (하위 폴더는 보지 않음)."""
    items = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if not entry.is_file(follow_symlinks=False):
                continue
            ext = os.path.splitext(entry.name)[1].lower()
            if not include_all and ext not in IMAGE_EXTENSIONS:
                continue
            st = entry.stat()
            items.append(FileItem(entry.path, st.st_size, st.st_mtime))
    return items


def sort_files(items, order="name"):
    if order == "date":
        return sorted(items, key=lambda f: (f.mtime, os.path.basename(f.path).lower()))
    return sorted(items, key=lambda f: os.path.basename(f.path).lower())


def plan_groups(items, limit):
    """정렬 순서를 유지하면서, 각 그룹 합계가 limit 이하가 되도록 나눈다.

    한 파일이 limit보다 크면 그 파일 하나만 단독 그룹이 된다.
    """
    if limit <= 0:
        raise ValueError("용량 제한은 0보다 커야 합니다.")
    groups = []
    current = Group()
    for item in items:
        if current.files and current.total + item.size > limit:
            groups.append(current)
            current = Group()
        current.files.append(item)
        current.total += item.size
    if current.files:
        groups.append(current)
    return groups


def group_folder_names(base_name, count):
    width = max(2, len(str(count)))
    return [f"{base_name}_{i:0{width}d}" for i in range(1, count + 1)]


def _unique_path(path):
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{root} ({n}){ext}"):
        n += 1
    return f"{root} ({n}){ext}"


def execute(groups, output_dir, base_name, move=False, progress=None, should_stop=None):
    """그룹별 폴더를 만들고 파일을 복사/이동한다. 처리한 파일 수를 반환한다."""
    names = group_folder_names(base_name, len(groups))
    total_files = sum(len(g.files) for g in groups)
    done = 0
    for name, group in zip(names, groups):
        target_dir = os.path.join(output_dir, name)
        os.makedirs(target_dir, exist_ok=True)
        for item in group.files:
            if should_stop and should_stop():
                return done
            dest = _unique_path(os.path.join(target_dir, os.path.basename(item.path)))
            if move:
                shutil.move(item.path, dest)
            else:
                shutil.copy2(item.path, dest)
            done += 1
            if progress:
                progress(done, total_files, item.path)
    return done


def format_size(size):
    if size >= GB:
        return f"{size / GB:.2f} GB"
    if size >= MB:
        return f"{size / MB:.1f} MB"
    return f"{size / 1024:.0f} KB"
