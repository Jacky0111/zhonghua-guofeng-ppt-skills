#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
用法：
  ./install.sh <skill-id> [目标 skills 目录]
  ./install.sh --platform <平台> [--project <项目目录>] <skill-id>

平台（默认 agents）：
  agents、codex、copilot、opencode、kimi、openclaw   ~/.agents/skills
  claude                                             ~/.claude/skills（遵循 CLAUDE_CONFIG_DIR）
  hermes                                             ~/.hermes/skills
  grok                                               ~/.grok/skills

--project 改为安装到指定项目内的对应目录。
本脚本不向豆包安装；风格 Skill 请用 python3 tooling/package_doubao.py 打包上传。
EOF
}

fail() {
  echo "$1" >&2
  exit 2
}

skill_id=""
custom_root=""
platform=""
project=""
positional=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --platform|--project)
      if [[ $# -lt 2 || -z "$2" || "$2" == -* ]]; then
        fail "选项 $1 需要一个值。"
      fi
      if [[ "$1" == "--platform" ]]; then platform="$2"; else project="$2"; fi
      shift 2
      ;;
    -*)
      fail "未知选项：$1"
      ;;
    *)
      positional=$((positional + 1))
      case "$positional" in
        1) skill_id="$1" ;;
        2) custom_root="$1" ;;
        *) usage >&2; exit 2 ;;
      esac
      shift
      ;;
  esac
done

if [[ $positional -lt 1 ]]; then
  usage >&2
  exit 2
fi
if [[ ! "$skill_id" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  fail "Skill ID 格式无效：${skill_id}"
fi
if [[ -n "$custom_root" && -n "${platform}${project}" ]]; then
  fail "目标目录不能与 --platform 或 --project 同时使用。"
fi

platform="${platform:-agents}"
case "$platform" in
  agents|codex|copilot|opencode|kimi|openclaw)
    user_root="${HOME}/.agents/skills"
    project_subdir=".agents/skills"
    ;;
  claude)
    user_root="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}/skills"
    project_subdir=".claude/skills"
    ;;
  hermes)
    user_root="${HOME}/.hermes/skills"
    project_subdir=".agents/skills"
    ;;
  grok)
    user_root="${HOME}/.grok/skills"
    project_subdir=".grok/skills"
    ;;
  doubao)
    fail "本脚本不向豆包安装。风格 Skill 请打包上传：python3 tooling/package_doubao.py <风格 skill-id>"
    ;;
  deepseek)
    fail "DeepSeek 是模型提供方。请按实际使用的工具选择 --platform。"
    ;;
  *)
    fail "未知平台：${platform}（运行 ./install.sh --help 查看可选值）"
    ;;
esac

repo_root="$(cd "$(dirname "$0")" && pwd)"
source_dir="${repo_root}/.agents/skills/${skill_id}"
if [[ ! -f "${source_dir}/SKILL.md" ]]; then
  echo "未找到 Skill：${skill_id}" >&2
  exit 1
fi

if [[ -n "$custom_root" ]]; then
  skill_root="$custom_root"
elif [[ -n "$project" ]]; then
  if [[ ! -d "$project" ]]; then
    echo "项目目录不存在：${project}" >&2
    exit 1
  fi
  skill_root="${project%/}/${project_subdir}"
else
  skill_root="$user_root"
fi
target_dir="${skill_root}/${skill_id}"

mkdir -p "$skill_root"
if [[ -e "$target_dir" || -L "$target_dir" ]]; then
  echo "目标已存在：${target_dir}；为避免覆盖，请先移走或删除现有目录。" >&2
  exit 1
fi
cp -R "$source_dir" "$target_dir"
echo "已安装 ${skill_id} 到 ${target_dir}"

if [[ "$platform" == "hermes" && -n "$project" ]]; then
  # bash 3.2 的 printf %q 会拆坏多字节路径，改用单引号转义。
  quoted="'$(printf '%s' "$project" | sed "s/'/'\\\\''/g")'"
  echo "Hermes 须先信任项目才会加载项目内 Skill，请自行运行：hermes skills trust ${quoted}"
fi
if [[ "$platform" == "openclaw" && -z "$project" ]]; then
  echo "提示：OpenClaw 仅在默认状态目录下读取 ~/.agents/skills。"
fi
