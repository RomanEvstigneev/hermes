# External Skill Porting into Bundled Hermes Skills

Use this when a user asks to integrate skills from a third-party repository into Hermes' bundled skill library.

## Workflow

1. Clone or inspect the external repo and inventory all `SKILL.md` files, support files, frontmatter fields, and runtime-specific assumptions.
2. Decide whether each external skill should be:
   - ported as a new Hermes bundled class-level skill,
   - merged into an existing Hermes umbrella skill,
   - added as a support reference/template/script,
   - left as an optional external tap, or
   - rejected as too personal/runtime-specific.
3. For bundled Hermes skills, write directly under `skills/<category>/<skill-name>/SKILL.md`. Do not use `skill_manage(action='create')`, which targets the user-local skill tree.
4. Preserve license attribution in the `author` field or body when adapting MIT/open-source material, e.g. `author: Hermes Agent (adapted from <author>)`.
5. Normalize runtime assumptions:
   - Replace Claude Code slash-command/hook language with Hermes terminology.
   - Prefer `AGENTS.md` and Hermes tools/skills over Claude-only configuration.
   - Remove unsupported frontmatter such as `disable-model-invocation` unless Hermes has explicit support for it.
   - Convert one-off personal paths and product-specific conventions into configurable guidance or omit them.
6. Avoid duplicate triggers. If Hermes already has a class-level umbrella skill, patch it with the useful external guidance instead of adding a competing narrow skill.
7. New skills should be class-level and rich enough to stand alone: Overview, When to Use, Workflow, Pitfalls, Verification Checklist, and related skills metadata.
8. Validate frontmatter and size constraints for every new or patched skill.
9. Run targeted skill tests. Prefer `scripts/run_tests.sh`; if it fails before test collection due to a broken local venv (for example `venv/bin/python: No module named pip` while installing pytest plugins), use a narrow fallback pytest invocation and state that it is not CI-equivalent.

## Validation Snippet

```python
from pathlib import Path
import re, yaml

for path in Path('skills').glob('**/SKILL.md'):
    content = path.read_text()
    assert content.startswith('---'), path
    m = re.search(r'\n---\s*\n', content[3:])
    assert m, path
    fm = yaml.safe_load(content[3:m.start()+3])
    assert isinstance(fm, dict), path
    assert fm.get('name'), path
    assert fm.get('description'), path
    assert len(fm['description']) <= 1024, path
    assert len(content) <= 100_000, path
```

## Pitfalls

- Do not wholesale-import a third-party skill pack into bundled Hermes when it overlaps existing umbrellas.
- Do not preserve Claude-only hooks or personal path assumptions in Hermes bundled skills.
- Do not create long flat lists of narrow skills when the useful learning belongs in an existing class-level skill.
- Do not claim full verification if the wrapper failed and only fallback pytest ran.
