#!/usr/bin/env python3
"""Validate bilingual style and workflow skill exports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

FORBIDDEN_PATHS = ("/Users/", "/home/")
PACKAGE_ROOTS = ("styles", "workflows")
SKILLS_DIR = ".agents/skills"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_repo(repo: Path) -> tuple[list[str], dict[str, set[str]]]:
    errors: list[str] = []
    ids_by_kind: dict[str, set[str]] = {}
    for kind in PACKAGE_ROOTS:
        catalog = repo / "catalog" / f"{kind}.json"
        try:
            ids_by_kind[kind] = {item["id"] for item in json.loads(catalog.read_text(encoding="utf-8"))[kind]}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{repo.name}/catalog/{kind}.json 无效：{exc}")
            ids_by_kind[kind] = set()
    skills = repo / SKILLS_DIR
    folders = {p.name for p in skills.iterdir() if p.is_dir() and not p.name.startswith(".")} if skills.is_dir() else set()
    listed = set().union(*ids_by_kind.values())
    if folders != listed:
        errors.append(f"{repo.name} {SKILLS_DIR} 与 catalog 不一致：{sorted(folders ^ listed)}")
    for kind in PACKAGE_ROOTS:
        for skill_id in sorted(ids_by_kind[kind]):
            folder = skills / skill_id
            required = ["SKILL.md", "agents/openai.yaml"]
            if kind == "styles":
                required.append("assets/README.md")
            for rel in required:
                if not (folder / rel).is_file():
                    errors.append(f"{repo.name}/{skill_id} 缺少 {rel}")
            metadata = folder / "agents/openai.yaml"
            if metadata.is_file():
                yaml_text = metadata.read_text(encoding="utf-8")
                for field in ("display_name:", "short_description:", "default_prompt:"):
                    if field not in yaml_text:
                        errors.append(f"{repo.name}/{skill_id}/agents/openai.yaml 缺少 {field}")
                if f"${skill_id}" not in yaml_text:
                    errors.append(f"{repo.name}/{skill_id}/agents/openai.yaml default_prompt 未提及稳定 ID")
            skill_file = folder / "SKILL.md"
            if skill_file.is_file():
                content = skill_file.read_text(encoding="utf-8")
                match = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", content)
                if not match or match.group(1) != skill_id:
                    errors.append(f"{repo.name}/{skill_id} 的 frontmatter name 与目录 ID 不一致")
                for forbidden in FORBIDDEN_PATHS:
                    if forbidden in content:
                        errors.append(f"{repo.name}/{skill_id}/SKILL.md 含环境路径或预览路径：{forbidden}")
                if kind == "styles":
                    for raw in re.findall(r"`((?:assets|references)/[^`]+)`", content):
                        if not (folder / raw).exists():
                            errors.append(f"{repo.name}/{skill_id}/SKILL.md 路径不存在：{raw}")
            for md in folder.rglob("*.md"):
                content = md.read_text(encoding="utf-8")
                for destination in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
                    if destination.startswith(("https://", "http://", "mailto:")) or destination.startswith("#"):
                        continue
                    target = (md.parent / destination.split("#", 1)[0]).resolve()
                    if not target.exists():
                        errors.append(f"{md.relative_to(repo)} 链接断开：{destination}")
                if any(path in content for path in FORBIDDEN_PATHS):
                    errors.append(f"{md.relative_to(repo)} 含绝对本地路径或临时预览路径")
    for rel in ("install.sh", "LICENSE", "LICENSE-CONTENT.md", "NOTICE.md"):
        if not (repo / rel).is_file():
            errors.append(f"{repo.name} 缺少 {rel}")
    return errors, ids_by_kind


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true", help="将未清权风格素材视为阻断错误")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    repos_parent = root / "repositories"
    repos = [repos_parent / locale for locale in ("zh-CN", "en") if (repos_parent / locale).is_dir()]
    standalone = not repos
    if standalone:
        repos = [root]
    all_errors: list[str] = []
    results = []
    for repo in repos:
        errors, ids_by_kind = validate_repo(repo)
        all_errors.extend(errors)
        results.append(ids_by_kind)
    if len(results) == 2:
        for kind in PACKAGE_ROOTS:
            if results[0][kind] != results[1][kind]:
                all_errors.append(f"中英文 {kind} Skill ID 集合不一致")
        for kind in PACKAGE_ROOTS:
            for skill_id in sorted(results[0][kind] & results[1][kind]):
                zh = repos[0] / SKILLS_DIR / skill_id
                en = repos[1] / SKILLS_DIR / skill_id
                zh_files = {p.relative_to(zh).as_posix() for p in zh.rglob("*") if p.is_file()}
                en_files = {p.relative_to(en).as_posix() for p in en.rglob("*") if p.is_file()}
                if zh_files != en_files:
                    all_errors.append(f"{skill_id} 中英文文件结构不一致")
                    continue
                for rel in sorted(zh_files):
                    if rel.startswith("assets/") and not rel.endswith(".md") and digest(zh / rel) != digest(en / rel):
                        all_errors.append(f"{skill_id} 中英文资源内容不一致：{rel}")
    if args.release:
        for repo in repos:
            catalog = repo / "catalog/styles.json"
            if catalog.is_file():
                for style in json.loads(catalog.read_text(encoding="utf-8"))["styles"]:
                    if style.get("assetRights") != "cleared":
                        all_errors.append(f"发布阻断：{repo.name}/{style['id']} 素材状态为 {style.get('assetRights')}")
    if all_errors:
        print("检查失败：", file=sys.stderr)
        for error in all_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    total = sum(len(ids) for ids in results[0].values()) if results else 0
    print(f"检查通过：{'单一发行目录' if standalone else '中英文发行目录'}；Skill 数：{total}。")
    if not args.release:
        print("发布授权状态需另行核验；可用 --release 检查发布门槛。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
