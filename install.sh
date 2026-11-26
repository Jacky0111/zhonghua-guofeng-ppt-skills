#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "用法：./install.sh <skill-id> [目标 skills 目录]" >&2
  exit 2
fi

skill_id="$1"
if [[ ! "$skill_id" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "Skill ID 格式无效：$skill_id" >&2
  exit 2
fi
repo_root="$(cd "$(dirname "$0")" && pwd)"
source_dir="$repo_root/.agents/skills/$skill_id"
skill_root="${2:-$HOME/.agents/skills}"
target_dir="$skill_root/$skill_id"

if [[ ! -f "$source_dir/SKILL.md" ]]; then
  echo "未找到 Skill：$skill_id" >&2
  exit 1
fi

mkdir -p "$skill_root"
if [[ -e "$target_dir" ]]; then
  echo "目标已存在：${target_dir}；为避免覆盖，请先移走或删除现有目录。" >&2
  exit 1
fi
cp -R "$source_dir" "$target_dir"
echo "已安装 $skill_id 到 $target_dir"
