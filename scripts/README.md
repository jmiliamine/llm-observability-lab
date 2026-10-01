# scripts

Small helpers called by the Task commands. Plain Python so they behave the same on Windows,
macOS and Linux.

| Script | Called by | What it does |
|---|---|---|
| `doctor.py` | `task doctor` | Checks the tools, Docker memory, free ports, Ollama and the kubectl/server version gap |
| `gen_observability.py` | `task gen`, `task lint` | Builds the Grafana dashboard and wraps the alert rules and the database init script into Kubernetes objects. `--check` fails if the generated files are out of date |
| `stage_notes.py` | `task app:build` | Copies the `.md` and `.txt` files of a notes folder into `build/corpus/`, the only folder the image build can see |
| `set_image_tag.py` | `task app:build` | Writes the git-ignored overlay that pins the image tag of the last build |
