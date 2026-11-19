# Contributing to IontrapdesignBot

Thank you for contributing! Bug reports, reproducible research cases, documentation improvements, geometry generators, numerical methods, and tests are all welcome.

## Development setup

```bash
git clone https://github.com/zipeilee/IontrapdesignBot.git
cd IontrapdesignBot
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest tests/ -q
```

## Workflow

1. Open an issue for substantial changes so the design can be discussed first.
2. Fork the repository and create a focused branch from `main`.
3. Keep changes scoped and include documentation for user-visible behavior.
4. Add or update tests for bug fixes and new features.
5. Run the full test suite before submitting a pull request.
6. Describe the motivation, implementation, validation, and any limitations in the pull request.

## Numerical and physics changes

Changes to geometry, BEM, trap characterization, optimization, or DC voltage synthesis should include appropriate validation:

- regression tests for fixed defects;
- analytical or symmetry-based benchmarks where available;
- mesh/panel-convergence checks for numerical results;
- explicit units and assumptions;
- a clear statement of applicability and limitations.

Do not report a geometry as fabrication-ready solely because the built-in spacing check passes.

## Code and documentation guidelines

- Follow the existing Python style and prefer small, readable, typed interfaces.
- Keep electrode dimensions in micrometres unless an interface explicitly states otherwise.
- Preserve electrode names and kinds when extending layout I/O.
- Update [`docs/tools.md`](docs/tools.md), relevant skills, and both README language versions when changing public MCP tools.
- Do not commit `.venv/`, caches, local credentials, generated videos, or private design data.
- Do not commit API keys, access tokens, or other secrets. The `execute_script` tool is intentionally powerful; do not expose it to untrusted users or networks.

## Attribution

IontrapdesignBot was inspired by [KlayoutClaw](https://github.com/caidish/KlayoutClaw), created by [@caidish](https://github.com/caidish). Please preserve the attribution in the README. If you reuse material from another project, verify its license and include the required copyright and license notices.

By contributing, you agree that your contribution may be distributed under the repository's [MIT License](LICENSE).
