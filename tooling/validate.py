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
LANGUAGE_HEADINGS = {"zh-CN": "## 多语言生成", "en": "## Multilingual output"}
UNRELEASED = ("未发布", "Unreleased")
REQUIRED_FILES = (".gitignore", "CHANGELOG.md", "CONTRIBUTING.md", "DESIGN-PRINCIPLES.md", "KNOWN-ISSUES.md",
                  "LICENSE", "LICENSE-CONTENT.md", "NOTICE.md", "README.md", "RELEASE-CHECKLIST.md", "VERSION",
                  "install.sh", "tooling/validate.py", "tooling/package_doubao.py",
                  "SECURITY.md", "CODE_OF_CONDUCT.md", ".github/pull_request_template.md",
                  ".github/workflows/validate.yml")
STYLE_KEYS = {"id", "version", "category", "locales", "assetRights", "references"}
ASSET_RIGHTS = {"cleared", "review-required", "local-only"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_versions(repo: Path) -> list[str]:
    errors: list[str] = []
    try:
        version = (repo / "VERSION").read_text(encoding="utf-8").strip()
        changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
        readme = (repo / "README.md").read_text(encoding="utf-8")
        items = [item for kind in PACKAGE_ROOTS
                 for item in json.loads((repo / "catalog" / f"{kind}.json").read_text(encoding="utf-8"))[kind]]
    except (OSError, ValueError, KeyError) as exc:
        return [f"{repo.name} 无法检查版本 cannot check versions: {exc}"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append(f"{repo.name}/VERSION 格式无效 invalid: {version}")
    latest = re.search(r"(?m)^## \[([^\]]+)\]", changelog)
    if not latest or latest.group(1) != version:
        errors.append(f"{repo.name}/CHANGELOG.md 最新版本与 VERSION 不一致 latest entry differs")
    for item in items:
        if item.get("version") != version:
            errors.append(f"{repo.name}/{item.get('id')} 版本不一致 version differs: {item.get('version')}")
        row = re.search(rf"(?m)^\| `{re.escape(str(item.get('id')))}` \|.*\| `([^`]+)` \|$", readme)
        if row and row.group(1) != version:
            errors.append(f"{repo.name}/README.md 版本不一致 version differs: {item.get('id')}")
        if not row and "category" in item:
            errors.append(f"{repo.name}/README.md 缺少版本表行 missing version row: {item.get('id')}")
    header = re.search(r"(?:版本|Version) (?:<code>|`)([^<`]+)", readme)
    if not header or header.group(1) != version:
        errors.append(f"{repo.name}/README.md 页眉版本缺失或不一致 header version missing or differs")
    return errors


def local_links(text: str) -> list[str]:
    found = re.findall(r"\]\(([^)\s]+)\)|(?:src|href)=\"([^\"]+)\"", text)
    return [a or b for a, b in found if not (a or b).startswith(("https://", "http://", "mailto:", "#"))]


def validate_root_documents(repo: Path) -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_FILES:
        if not (repo / rel).is_file():
            errors.append(f"{repo.name} 缺少 missing {rel}")
    for md in sorted(repo.glob("*.md")):
        content = md.read_text(encoding="utf-8")
        for destination in local_links(content):
            if not (repo / destination.split("#", 1)[0]).exists():
                errors.append(f"{repo.name}/{md.name} 链接断开 broken link: {destination}")
        if any(path in content for path in FORBIDDEN_PATHS):
            errors.append(f"{repo.name}/{md.name} 含绝对本地路径 contains an absolute local path")
    return errors


def validate_style_entries(repo: Path) -> list[str]:
    errors: list[str] = []
    try:
        styles = json.loads((repo / "catalog/styles.json").read_text(encoding="utf-8"))["styles"]
        for style in styles:
            name = f"{repo.name}/{style['id']}"
            if set(style) - STYLE_KEYS or style.get("assetRights") not in ASSET_RIGHTS:
                errors.append(f"{name} 目录字段不符合 Schema catalog entry violates the schema")
            for ref in style.get("references", []):
                if not (repo / ref).is_file():
                    errors.append(f"{name} 引用不存在 missing reference: {ref}")
            examples = sorted(p.name[:2] for p in (repo / SKILLS_DIR / style["id"] / "assets/examples").glob("*.png"))
            if examples != ["01", "02", "03", "04", "05"]:
                errors.append(f"{name} 示例须为 01–05 五张 needs examples 01-05")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"{repo.name}/catalog/styles.json 无效 invalid: {exc}")
    return errors


def validate_language_sections(repo: Path, skill_ids: set[str]) -> list[str]:
    """Every skill must end with the same canonical multilingual section."""
    references = repo / SKILLS_DIR / "chinese-style-skill-workflow/references"
    canonical = {}
    for locale in LANGUAGE_HEADINGS:
        path = references / f"multilingual-section.{locale}.md"
        if not path.is_file():
            return [f"{repo.name} 缺少 missing {path.name}"]
        canonical[locale] = path.read_text(encoding="utf-8").strip()
    locale = repo.name if repo.name in canonical else None
    errors: list[str] = []
    for skill_id in sorted(skill_ids):
        skill = repo / SKILLS_DIR / skill_id / "SKILL.md"
        if not skill.is_file():
            continue
        content = skill.read_text(encoding="utf-8")
        if locale is None:
            locale = next((k for k, h in LANGUAGE_HEADINGS.items() if f"\n{h}\n" in content), None)
        start = content.find(f"\n{LANGUAGE_HEADINGS[locale]}\n") if locale else -1
        if start < 0 or content[start:].strip() != canonical[locale]:
            errors.append(f"{repo.name}/{skill_id} 多语言章节缺失或与标准文本不一致 multilingual section missing or altered")
    return errors


def validate_repo(repo: Path) -> tuple[list[str], dict[str, set[str]]]:
    errors: list[str] = []
    ids_by_kind: dict[str, set[str]] = {}
    for kind in PACKAGE_ROOTS:
        catalog = repo / "catalog" / f"{kind}.json"
        try:
            ids_by_kind[kind] = {item["id"] for item in json.loads(catalog.read_text(encoding="utf-8"))[kind]}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{repo.name}/catalog/{kind}.json 无效 invalid: {exc}")
            ids_by_kind[kind] = set()
    skills = repo / SKILLS_DIR
    folders = {p.name for p in skills.iterdir() if p.is_dir() and not p.name.startswith(".")} if skills.is_dir() else set()
    listed = set().union(*ids_by_kind.values())
    if folders != listed:
        errors.append(f"{repo.name} {SKILLS_DIR} 与 catalog 不一致 does not match catalog: {sorted(folders ^ listed)}")
    for kind in PACKAGE_ROOTS:
        for skill_id in sorted(ids_by_kind[kind]):
            folder = skills / skill_id
            required = ["SKILL.md", "agents/openai.yaml"]
            if kind == "styles":
                required.append("assets/README.md")
            for rel in required:
                if not (folder / rel).is_file():
                    errors.append(f"{repo.name}/{skill_id} 缺少 missing {rel}")
            metadata = folder / "agents/openai.yaml"
            if metadata.is_file():
                yaml_text = metadata.read_text(encoding="utf-8")
                for field in ("display_name:", "short_description:", "default_prompt:"):
                    if field not in yaml_text:
                        errors.append(f"{repo.name}/{skill_id}/agents/openai.yaml 缺少 missing {field}")
                if f"${skill_id}" not in yaml_text:
                    errors.append(f"{repo.name}/{skill_id}/agents/openai.yaml default_prompt 未提及稳定 ID lacks the stable ID")
            skill_file = folder / "SKILL.md"
            if skill_file.is_file():
                content = skill_file.read_text(encoding="utf-8")
                match = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", content)
                if not match or match.group(1) != skill_id:
                    errors.append(f"{repo.name}/{skill_id} 的 frontmatter name 与目录 ID 不一致 name differs from folder ID")
                for forbidden in FORBIDDEN_PATHS:
                    if forbidden in content:
                        errors.append(f"{repo.name}/{skill_id}/SKILL.md 含环境路径 contains a machine path: {forbidden}")
                if kind == "styles":
                    for raw in re.findall(r"`((?:assets|references)/[^`]+)`", content):
                        if not (folder / raw).exists():
                            errors.append(f"{repo.name}/{skill_id}/SKILL.md 路径不存在 missing path: {raw}")
            for md in folder.rglob("*.md"):
                content = md.read_text(encoding="utf-8")
                for destination in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
                    if destination.startswith(("https://", "http://", "mailto:")) or destination.startswith("#"):
                        continue
                    target = (md.parent / destination.split("#", 1)[0]).resolve()
                    if not target.exists():
                        errors.append(f"{md.relative_to(repo)} 链接断开 broken link: {destination}")
                if any(path in content for path in FORBIDDEN_PATHS):
                    errors.append(f"{md.relative_to(repo)} 含绝对本地路径 contains an absolute local path")
    errors.extend(validate_root_documents(repo))
    errors.extend(validate_versions(repo))
    errors.extend(validate_style_entries(repo))
    errors.extend(validate_language_sections(repo, listed))
    return errors, ids_by_kind


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true", help="将未清权风格素材视为阻断错误 / treat uncleared assets as errors")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    repos_parent = root / "repositories"
    repos = [repos_parent / locale for locale in ("zh-CN", "en") if (repos_parent / locale).is_dir()]
    standalone = not repos
    if standalone:
        repos = [root]
    all_errors: list[str] = []
    results = []
    if not standalone and len(repos) != 2:
        all_errors.append("repositories/ 须同时包含 zh-CN 与 en / must contain both zh-CN and en")
    for repo in repos:
        errors, ids_by_kind = validate_repo(repo)
        all_errors.extend(errors)
        results.append(ids_by_kind)
    if len(results) == 2:
        for kind in PACKAGE_ROOTS:
            if results[0][kind] != results[1][kind]:
                all_errors.append(f"中英文 {kind} Skill ID 集合不一致 ID sets differ")
        for kind in PACKAGE_ROOTS:
            for skill_id in sorted(results[0][kind] & results[1][kind]):
                zh = repos[0] / SKILLS_DIR / skill_id
                en = repos[1] / SKILLS_DIR / skill_id
                zh_files = {p.relative_to(zh).as_posix() for p in zh.rglob("*") if p.is_file()}
                en_files = {p.relative_to(en).as_posix() for p in en.rglob("*") if p.is_file()}
                if zh_files != en_files:
                    all_errors.append(f"{skill_id} 中英文文件结构不一致 file structure differs")
                    continue
                for rel in sorted(zh_files):
                    if rel.startswith("assets/") and not rel.endswith(".md") and digest(zh / rel) != digest(en / rel):
                        all_errors.append(f"{skill_id} 中英文资源内容不一致 asset content differs: {rel}")
    if len(repos) == 2:
        listing = [{p.relative_to(r).as_posix() for p in r.rglob("*") if p.is_file()
                    and not {".git", ".claude", "__pycache__"} & set(p.relative_to(r).parts)
                    and p.relative_to(r).parts[0] != "dist"
                    and p.name != ".DS_Store"} for r in repos]
        if listing[0] != listing[1]:
            all_errors.append(f"中英文文件清单不一致 file lists differ: {sorted(listing[0] ^ listing[1])}")
        if (repos[0] / "VERSION").is_file() and (repos[1] / "VERSION").is_file():
            if (repos[0] / "VERSION").read_text() != (repos[1] / "VERSION").read_text():
                all_errors.append("中英文版本不一致 repository versions differ")
    if not standalone and len(repos) == 2:
        # Workspace copies must match the Chinese export.
        for name in ("styles.json", "workflows.json"):
            source, mirror = repos[0] / "catalog" / name, root / "catalog" / name
            if source.is_file() and (not mirror.is_file() or mirror.read_bytes() != source.read_bytes()):
                all_errors.append(f"根 catalog/{name} 与发行目录不一致 root catalog differs")
        version_file, readme = repos[0] / "VERSION", root / "README.md"
        if version_file.is_file() and readme.is_file():
            version = version_file.read_text(encoding="utf-8").strip()
            rows = re.findall(r"(?m)^\| `[a-z0-9-]+` \|.*\| `([^`]+)` \|$", readme.read_text(encoding="utf-8"))
            if any(row != version for row in rows):
                all_errors.append("根 README.md 版本不一致 root README version differs")
    if args.release:
        for repo in repos:
            changelog = repo / "CHANGELOG.md"
            if changelog.is_file():
                latest = re.search(r"(?m)^## \[[^\]]+\].*$", changelog.read_text(encoding="utf-8"))
                if latest and any(word in latest.group(0) for word in UNRELEASED):
                    all_errors.append(f"发布阻断 release blocked: {repo.name}/CHANGELOG.md 尚未填写发布日期 has no release date")
            try:
                styles = json.loads((repo / "catalog/styles.json").read_text(encoding="utf-8"))["styles"]
                for style in styles:
                    if style.get("assetRights") != "cleared":
                        all_errors.append(f"发布阻断 release blocked: {repo.name}/{style['id']} assetRights = {style.get('assetRights')}")
            except (OSError, ValueError, KeyError, TypeError):
                all_errors.append(f"发布阻断 release blocked: {repo.name}/catalog/styles.json 无法读取 unreadable")
    if all_errors:
        print("检查失败 Validation failed:", file=sys.stderr)
        for error in all_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    total = sum(len(ids) for ids in results[0].values()) if results else 0
    scope = "单一发行目录 single repository" if standalone else "中英文发行目录 both repositories"
    print(f"检查通过 Validation passed: {scope}; Skills: {total}.")
    if standalone:
        print("单仓库模式未检查中英文一致性 / Single-repository mode does not check bilingual parity.")
    if not args.release:
        print("发布授权状态需另行核验 / Run with --release to check the release gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
