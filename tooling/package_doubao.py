#!/usr/bin/env python3
"""Build one Doubao upload ZIP per style skill.

Source skills are never modified: images are downscaled and metadata is added
only inside the package. Requires `cwebp` and `dwebp` (libwebp).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SKILLS_DIR = ".agents/skills"
DEFAULT_OUTPUT = "dist/doubao"
IMAGE_WIDTH = 1280

# Limits from the Doubao skill development specification (checked 2026-11-26).
# The page writes "MB" without defining it, so the stricter decimal value applies.
MAX_ZIP_BYTES = 16_000_000
MAX_TOTAL_BYTES = 16_000_000
MAX_FILE_BYTES = 2_000_000
MAX_ENTRIES = 1024
MAX_NAME = 64
MAX_DESCRIPTION = 300
MAX_DISPLAY_NAME = 128
MAX_DISPLAY_DESCRIPTION = 300

NOTES = """# Package notes / 打包说明

- Skill: {skill_id}, version {version}
- Images wider than {width}px were downscaled to {width}px for upload size limits.
  宽度超过 {width}px 的图片为满足上传限制已缩小到 {width}px。
- `metadata` was added to SKILL.md and `agents/` was left out.
  SKILL.md 增加了 `metadata`，未包含 `agents/`。
- Images are AI-generated; see NOTICE.md. 图片由 AI 生成，见 NOTICE.md。
- Downscaled images no longer carry their embedded C2PA content credentials;
  the originals are in the repository. 缩小后的图片不含原内容凭证，原件见仓库。
- License / 许可: CC BY 4.0, see LICENSE-CONTENT.md.
"""


class PackageError(Exception):
    pass


def png_width(path: Path) -> int:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise PackageError(f"不是有效 PNG not a valid PNG: {path.name}")
    return struct.unpack(">I", header[16:20])[0]


def downscale(path: Path, scratch: Path) -> None:
    intermediate = scratch / "resized.webp"
    result = scratch / "resized.png"
    commands = (
        ["cwebp", "-quiet", "-lossless", "-exact", "-resize", str(IMAGE_WIDTH), "0",
         str(path), "-o", str(intermediate)],
        ["dwebp", "-quiet", str(intermediate), "-o", str(result)],
    )
    for command in commands:
        done = subprocess.run(command, capture_output=True, text=True)
        if done.returncode != 0:
            raise PackageError(f"{command[0]} 失败 failed on {path.name}: {done.stderr.strip()}")
    shutil.move(str(result), str(path))


def scalar(raw: str) -> str:
    """Read a one-line YAML scalar, rejecting plain values YAML could misread."""
    value = raw.strip()
    if value.startswith('"'):
        try:
            return json.loads(value)
        except ValueError as exc:
            raise PackageError(f"无法解析引号字符串 cannot parse quoted string: {value}") from exc
    if not value or value[0] in "'[]{}&*!|>%@`#-?:," or ": " in value or " #" in value or value.endswith(":"):
        raise PackageError(f"YAML 值需要加双引号 value must be double-quoted: {value}")
    return value


def field(block: str, key: str, source: str) -> str:
    match = re.search(rf"(?m)^[ \t]*{key}:[ \t]*(.*)$", block)
    if not match:
        raise PackageError(f"{source} 缺少 missing {key}")
    return scalar(match.group(1))


def check_length(label: str, value: str, limit: int) -> None:
    if not value.strip() or len(value) > limit:
        raise PackageError(f"{label} 长度须为 1–{limit} 个字符 must be 1-{limit} characters, got {len(value)}")


def add_metadata(skill_id: str, source: Path, staging: Path) -> None:
    skill_file = staging / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", content, re.S)
    if not match:
        raise PackageError("SKILL.md 缺少 frontmatter missing frontmatter")
    frontmatter = match.group(1)
    name = field(frontmatter, "name", "SKILL.md")
    check_length("name", name, MAX_NAME)
    if name != skill_id or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        raise PackageError(f"name 无效或与目录不一致 invalid name or differs from folder: {name}")
    check_length("description", field(frontmatter, "description", "SKILL.md"), MAX_DESCRIPTION)
    if re.search(r"(?m)^metadata:", frontmatter):
        raise PackageError("SKILL.md 已有 metadata，需更新打包脚本 already has metadata; update this script")
    interface = source / "agents/openai.yaml"
    if not interface.is_file():
        raise PackageError("缺少 missing agents/openai.yaml")
    yaml_text = interface.read_text(encoding="utf-8")
    display_name = field(yaml_text, "display_name", "agents/openai.yaml")
    display_description = field(yaml_text, "short_description", "agents/openai.yaml")
    check_length("display_name", display_name, MAX_DISPLAY_NAME)
    check_length("display_description", display_description, MAX_DISPLAY_DESCRIPTION)
    metadata = (
        "metadata:\n"
        f"  display_name: {json.dumps(display_name, ensure_ascii=False)}\n"
        f"  display_description: {json.dumps(display_description, ensure_ascii=False)}\n"
    )
    skill_file.write_text(
        f"---\n{frontmatter}\n{metadata}---\n{content[match.end():]}", encoding="utf-8"
    )


def add_known_issues(repo: Path, skill_id: str, staging: Path) -> None:
    """Keep only this skill's rows and make their links relative to the package."""
    source = repo / "KNOWN-ISSUES.md"
    if not source.is_file() or (staging / source.name).exists():
        raise PackageError(f"无法加入 cannot add {source.name}")
    lines = source.read_text(encoding="utf-8").splitlines()
    table = [line for line in lines if line.startswith("|")]
    if len(table) < 2:
        raise PackageError(f"{source.name} 缺少问题表格 has no issue table")
    prefix = f"]({SKILLS_DIR}/{skill_id}/"
    rows = [line.replace(prefix, "](") for line in table[2:] if prefix in line]
    if rows:
        kept = lines[: lines.index(table[0])] + table[:2] + rows
    else:
        kept = [lines[0], "", "No listed issues for this skill. 本 Skill 暂无已登记问题。"]
    (staging / source.name).write_text("\n".join(kept) + "\n", encoding="utf-8")


def check_references(staging: Path) -> None:
    root = staging.resolve()
    for document in sorted(staging.rglob("*.md")):
        content = document.read_text(encoding="utf-8")
        targets = [
            document.parent / link.split("#", 1)[0]
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)
            if not link.startswith(("https://", "http://", "mailto:", "#"))
        ]
        if document == staging / "SKILL.md":
            targets += [staging / raw for raw in re.findall(r"`((?:assets|references|scripts)/[^`]+)`", content)]
        for path in targets:
            target = path.resolve()
            if root not in (target, *target.parents) or not target.exists():
                name = document.relative_to(staging).as_posix()
                raise PackageError(f"{name} 引用的路径不在包内 referenced path not in package: {path.name}")


def build(repo: Path, skill_id: str, version: str, output: Path) -> str:
    source = repo / SKILLS_DIR / skill_id
    target = output / f"{skill_id}.zip"
    if target.exists():
        target.unlink()  # never leave a stale package behind after a failed build
    if not (source / "SKILL.md").is_file():
        raise PackageError("未找到 SKILL.md not found")
    with tempfile.TemporaryDirectory() as temp:
        scratch = Path(temp)
        staging = scratch / skill_id
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if relative.parts[0] == "agents" or any(part.startswith(".") for part in relative.parts):
                continue
            if path.is_symlink():
                raise PackageError(f"不支持软链接 symlinks are not supported: {relative}")
            if path.is_file():
                (staging / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, staging / relative)
        for image in sorted(staging.rglob("*.png")):
            if png_width(image) > IMAGE_WIDTH:
                downscale(image, scratch)
        add_metadata(skill_id, source, staging)
        add_known_issues(repo, skill_id, staging)
        for name in ("LICENSE-CONTENT.md", "NOTICE.md"):
            if not (repo / name).is_file() or (staging / name).exists():
                raise PackageError(f"无法加入许可文件 cannot add license file: {name}")
            shutil.copyfile(repo / name, staging / name)
        notes = NOTES.format(skill_id=skill_id, version=version, width=IMAGE_WIDTH)
        (staging / "PACKAGE-NOTES.md").write_text(notes, encoding="utf-8")
        check_references(staging)

        files = sorted(p for p in staging.rglob("*") if p.is_file())
        sizes = {p.relative_to(staging).as_posix(): p.stat().st_size for p in files}
        oversized = [f"{rel} ({size})" for rel, size in sizes.items() if size > MAX_FILE_BYTES]
        if oversized:
            raise PackageError(f"单文件超过 file over {MAX_FILE_BYTES} 字节 bytes: {', '.join(oversized)}")
        total = sum(sizes.values())
        if total > MAX_TOTAL_BYTES:
            raise PackageError(f"解压总量超限 unpacked size over limit: {total}")
        if len(files) > MAX_ENTRIES:
            raise PackageError(f"条目超限 too many entries: {len(files)}")

        archive_path = scratch / "package.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for path in files:
                # Fixed timestamp and mode keep rebuilds of unchanged input identical.
                info = zipfile.ZipInfo(path.relative_to(staging).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        zip_size = archive_path.stat().st_size
        if zip_size > MAX_ZIP_BYTES:
            raise PackageError(f"ZIP 超限 ZIP over limit: {zip_size}")
        output.mkdir(parents=True, exist_ok=True)
        shutil.move(str(archive_path), str(target))
    return (f"{skill_id}: ZIP {zip_size}, 解压 unpacked {total}, "
            f"最大单文件 largest file {max(sizes.values())}, 条目 entries {len(files)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按豆包限制逐个打包风格 Skill / package style skills for Doubao"
    )
    parser.add_argument("skill_ids", nargs="*", help="默认全部风格 Skill / default: all style skills")
    parser.add_argument("--output", type=Path, help=f"输出目录 output directory (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent

    missing = [tool for tool in ("cwebp", "dwebp") if shutil.which(tool) is None]
    if missing:
        print(f"缺少命令 missing commands: {', '.join(missing)}（安装 libwebp / install libwebp）", file=sys.stderr)
        return 1
    try:
        styles = json.loads((repo / "catalog/styles.json").read_text(encoding="utf-8"))["styles"]
        versions = {item["id"]: item["version"] for item in styles}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"无法读取 cannot read catalog/styles.json: {exc}", file=sys.stderr)
        return 1
    selected = args.skill_ids or list(versions)
    unknown = [skill_id for skill_id in selected if skill_id not in versions]
    if unknown:
        print(f"不是风格 Skill，不打包 not a style skill: {', '.join(unknown)}", file=sys.stderr)
        return 1

    output = args.output.resolve() if args.output else repo / DEFAULT_OUTPUT
    failed = 0
    for skill_id in selected:
        try:
            print(build(repo, skill_id, versions[skill_id], output))
        except (PackageError, OSError, UnicodeError) as exc:
            failed += 1
            print(f"{skill_id}: 打包失败 failed: {exc}", file=sys.stderr)
    print(f"完成 built {len(selected) - failed}/{len(selected)} → {output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
