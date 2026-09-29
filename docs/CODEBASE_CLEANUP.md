# Codebase cleanup

## What accumulated, and why

The repository combines three independently developed parts: Python CV and
briefing code, a DeepSpace scaffold with its own UI/backend, and a Figma Make
frontend that later became the primary presentation app.

Git commit `6a294c7` ("consolidate frontend and DeepSpace into main project")
imported both `CLAUDE.md` files along with the scaffolds. It added 128 files and
19,465 lines. `frontend/CLAUDE.md` contained only `@AGENTS.md`;
`deepspace/CLAUDE.md` only linked to `AGENTS.md`. The `.claude/skills/deepspace`
entry was a symlink to the shared `.agents` skill. These were compatibility
files supplied by the templates, not evidence that the owner used Claude.

Later feature iterations added alternative viewers, demo data, notification
paths and presentation code. Some additions were left behind when the UI
changed. Concrete examples are callbacks passed into components that never
invoke them, a ranking function never called by the notification bridge, and
two definitions of the same Python function. Python silently replaced the
first `aspect_change` definition with the second.

The dependency folders also contained signs of package-manager switching:
pnpm's `.ignored_*` copies in the frontend and a separate root-level install
with no root package manifest. Their exact originating shell commands are not
recorded in Git, so the cause of those local installs cannot be proved.

## Removed

| Files/code | Reason |
|---|---|
| `frontend/CLAUDE.md`, `deepspace/CLAUDE.md` | Unneeded Claude-specific pointers; actual project guidance remains in `AGENTS.md` |
| `deepspace/.claude/` | Claude-specific skill link; shared `.agents` skill retained |
| `frontend/.figma/` | Figma-host install/dev/deploy/preview/language-server wrappers and metadata; local app uses Vite directly |
| Figma plugins and metadata machinery in `frontend/vite.config.ts` | Removed hosted preview/story/error-overlay scaffolding; kept React, Tailwind, aliases and all API/WebSocket proxies |
| Figma placeholders in `frontend/index.html` | Replaced with ordinary HTML metadata, title and language; preserved no-index behavior with robots metadata and `public/robots.txt` |
| Root `node_modules/` | Orphaned install without a root package manifest; active Photon imports resolve under `deepspace/node_modules` |
| `frontend/node_modules/.ignored_*` | Stale package-manager replacement copies; active package links use `.pnpm` |
| `nearmiss-app/` | Only two Vite cache files remained; no application source or entrypoint |
| Unused HomePage counts and ChannelPage callbacks in `frontend/src/App.tsx` | Props were never read; removed their now-unreachable assignment/notification functions, state and imports |
| `RankedIncident` and `rankedIncident()` in `deepspace/src/server/notify-bridge.ts` | Neither was used by the running bridge; actual send path retained |
| First `aspect_change` in `cv/detect_collisions.py` | Shadowed by a later definition; removing it does not change the function Python executes |
| `concat_boxes` in `cv/track_objects.py` | No callers/imports; actual concatenation is done inline in `process_clip` |

Updated the frontend's agent instructions to describe the actual local setup,
and ignored `dist/` and `.vite/` directories to prevent generated files appearing
as source changes.

## Deliberately retained

* `frontend/` is the presentation UI. `deepspace/` supplies the API, schemas,
  realtime/auth providers, shared domain code, integration processes and an
  additional working UI. Deleting that second directory would break the first.
* DeepSpace's products/subscriptions files are conventional CLI inputs, even
  though ordinary imports do not mention them. Cron/job files are imported by
  `worker.ts` and tied to Durable Object bindings. They are not safe candidates
  for deletion solely because their current handlers are empty.
* `.agents/skills/deepspace` and `AGENTS.md` are project development instructions.
  They have a different purpose from the deleted Claude compatibility files.
* Tests, standalone CV diagnostic/viewer CLIs, input videos, model weights,
  previous audit outputs, Python virtual environment and `.tools` executables
  remain. A standalone CLI having no import callers does not make it dead code.
* Both sets of camera assets are referenced: the presentation app uses `/cv/`,
  while the DeepSpace UI's `DemoClip` uses `/cv-wall/`.
* Project-level dependency installs and their lockfiles are retained. The
  frontend has a pnpm lockfile; DeepSpace also has deployment/package-manager
  conventions. Removing a lockfile merely to reduce file count hurts installs.

## Active technical debt, not removed as dead code

`briefing/run_p1.py` constructs a hard-coded CAM-001 event with fixed track IDs,
time and evidence score. `frontend/src/App.tsx` also contains hard-coded
`CV_REPORT` entries. These are active demo paths, not fresh CV analysis. Their
presence explains why presentation claims can disagree with generated CV
outputs. Replacing them requires connecting the UI and notification flow to
one run's actual accepted events; deleting them alone changes product behavior.

The notification bridge sends automatically and the conversation process can
also trigger it. This cleanup did not run those processes or send messages.
The backend TypeScript check currently has `.ts` import-extension configuration
errors in the Photon CLI files; those are separate from dead-code cleanup.

This cleanup does not claim that all architectural duplication is solved. It
removes proven leftovers while retaining the dependencies and behavior of the
current app. The cleanup and explanatory documentation are grouped for a local Git commit;
publishing or pushing is a separate step.

## Verification

* Frontend production build passed.
* Frontend TypeScript check with unused locals/parameters enabled passed.
* Python CV unit tests: 3 passed.
* Backend unit tests: 36 passed, 6 failed. Running the committed HEAD source in
  an isolated temporary directory reproduced the exact same six failures.
  Existing failures concern responder availability/selection and priority ranking.
* Backend TypeScript check still reports six TS5097 errors in the unchanged
  Photon integration scripts (`.ts` import extensions).
* `git diff --check` passed. No live notification services were started.

## Follow-up documentation review

Added Mermaid architecture diagrams in the README and `docs/ARCHITECTURE.md`,
including the distinct CV-intake and fixed P1 notification paths. Corrected
`scripts/run_notifyc_demo.py` to default to backend port 5173 instead of the stale
8780 value and to print the actual backend startup command. The CLI help and
three CV unit tests pass. No generated camera data or analysis output is included
in these changes; tracked browser demo videos remain because both UIs use them.
