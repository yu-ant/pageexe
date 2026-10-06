"""사진 폴더를 지정한 용량 이하의 하위 폴더로 나누는 핵심 로직 (GUI와 분리)."""

import os
import shutil
import zipfile
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


def scan_subfolders(folder, include_all=False):
    """하위 폴더(모든 깊이) 안의 사진 파일 목록을 반환한다. 폴더 바로 아래 파일은 제외."""
    items = []
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        if os.path.normpath(root) == os.path.normpath(folder):
            continue
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if not include_all and ext not in IMAGE_EXTENSIONS:
                continue
            path = os.path.join(root, name)
            if os.path.islink(path):
                continue
            st = os.stat(path)
            items.append(FileItem(path, st.st_size, st.st_mtime))
    return items


def flatten(items, target_dir, move=False, progress=None, should_stop=None):
    """파일들을 target_dir 한 곳으로 꺼낸다. 이름이 겹치면 '이름 (1).jpg'로 저장. 처리 수 반환."""
    os.makedirs(target_dir, exist_ok=True)
    done = 0
    for item in items:
        if should_stop and should_stop():
            return done
        dest = _unique_path(os.path.join(target_dir, os.path.basename(item.path)))
        if move:
            shutil.move(item.path, dest)
        else:
            shutil.copy2(item.path, dest)
        done += 1
        if progress:
            progress(done, len(items), item.path)
    return done


def remove_empty_dirs(folder):
    """folder 아래의 빈 하위 폴더를 지운다 (folder 자체는 남김). 지운 개수 반환."""
    removed = 0
    for root, dirs, files in os.walk(folder, topdown=False):
        if os.path.normpath(root) == os.path.normpath(folder):
            continue
        try:
            os.rmdir(root)  # 비어 있을 때만 성공
            removed += 1
        except OSError:
            pass
    return removed


def sort_files(items, order="name"):
    if order == "date":
        return sorted(items, key=lambda f: (f.mtime, os.path.basename(f.path).lower()))
    return sorted(items, key=lambda f: os.path.basename(f.path).lower())


def zip_overhead(item):
    """zip 안에서 파일 하나가 내용 외에 차지하는 바이트(헤더 2개 + 파일 이름 2번), 여유 포함."""
    return 128 + 2 * len(os.path.basename(item.path).encode("utf-8"))


ZIP_END_RESERVE = 1024  # zip 끝부분 기록용 여유


def plan_groups(items, limit, for_zip=False):
    """정렬 순서를 유지하면서, 각 그룹 합계가 limit 이하가 되도록 나눈다.

    for_zip이면 zip 헤더 용량까지 더해서 zip 파일 크기가 limit을 넘지 않게 한다.
    한 파일이 limit보다 크면 그 파일 하나만 단독 그룹이 된다.
    """
    if limit <= 0:
        raise ValueError("용량 제한은 0보다 커야 합니다.")
    budget = limit - ZIP_END_RESERVE if for_zip else limit
    groups = []
    current = Group()
    for item in items:
        cost = item.size + (zip_overhead(item) if for_zip else 0)
        if current.files and current.total + cost > budget:
            groups.append(current)
            current = Group()
        current.files.append(item)
        current.total += cost
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


def execute_zip(groups, output_dir, base_name, progress=None, should_stop=None):
    """그룹마다 '<이름>_01.zip' 같은 압축 파일을 만든다 (원본은 그대로). 처리한 파일 수 반환.

    사진은 이미 압축된 형식이라 다시 압축하지 않고 그대로 담는다(빠름, 크기 예측 가능).
    중지하면 만들던 zip은 지운다.
    """
    os.makedirs(output_dir, exist_ok=True)
    names = group_folder_names(base_name, len(groups))
    total_files = sum(len(g.files) for g in groups)
    done = 0
    for name, group in zip(names, groups):
        zip_path = _unique_path(os.path.join(output_dir, name + ".zip"))
        used = set()
        stopped = False
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            for item in group.files:
                if should_stop and should_stop():
                    stopped = True
                    break
                arcname = _unique_arcname(os.path.basename(item.path), used)
                zf.write(item.path, arcname)
                done += 1
                if progress:
                    progress(done, total_files, item.path)
        if stopped:
            os.remove(zip_path)
            return done - len(used)  # 지운 zip에 들어 있던 파일은 빼고 센다
    return done


def _unique_arcname(name, used):
    candidate = name
    root, ext = os.path.splitext(name)
    n = 1
    while candidate.lower() in used:
        candidate = f"{root} ({n}){ext}"
        n += 1
    used.add(candidate.lower())
    return candidate


def format_size(size):
    if size >= GB:
        return f"{size / GB:.2f} GB"
    if size >= MB:
        return f"{size / MB:.1f} MB"
    return f"{size / 1024:.0f} KB"
