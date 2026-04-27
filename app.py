import logging
import os

import streamlit as st
from dotenv import load_dotenv

from knowledge_base import PET_CARE_KNOWLEDGE
from pawpal_system import Owner, Pet, Task, Scheduler
from rag_engine import RAGEngine

load_dotenv()


def _setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    fh = logging.FileHandler("pawpal_rag.log")
    fh.setFormatter(fmt)
    root.addHandler(fh)


_setup_logging()


@st.cache_resource
def get_rag_engine() -> RAGEngine:
    return RAGEngine(PET_CARE_KNOWLEDGE)


def build_pet_context(owner: Owner | None, scheduler) -> str:
    """Build a plain-text summary of the owner's pets and tasks for the AI prompt."""
    if owner is None:
        return "No owner or pets have been set up yet."

    lines = [
        f"Owner: {owner.name}",
        f"Daily time budget: {owner.available_minutes_per_day} minutes",
    ]

    for pet in owner.pets:
        lines.append(f"\nPet: {pet.name} ({pet.species})")
        incomplete = [t for t in pet.tasks if not t.completion_status]
        done_count = sum(1 for t in pet.tasks if t.completion_status)

        if incomplete:
            for t in incomplete:
                time_str = f" | starts {t.start_time}" if t.start_time else ""
                lines.append(
                    f"  - {t.description} | {t.frequency} | {t.duration_minutes} min"
                    f" | priority {t.priority}"
                    f" | {'required' if t.required else 'optional'}{time_str}"
                )
        else:
            lines.append("  - No active tasks scheduled")

        if done_count:
            lines.append(f"  ({done_count} task(s) already completed today)")

    if scheduler:
        scheduled, skipped = scheduler.generate_plan()
        total = sum(t.duration_minutes for t in scheduled)
        lines.append(
            f"\nScheduled today: {len(scheduled)} task(s) using"
            f" {total}/{owner.available_minutes_per_day} minutes"
        )
        if skipped:
            skipped_names = ", ".join(t.description for t in skipped)
            lines.append(f"Skipped (over budget): {skipped_names}")

    return "\n".join(lines)

# Session state init
if 'owner' not in st.session_state:
    st.session_state.owner = None
if 'scheduler' not in st.session_state:
    st.session_state.scheduler = None
if 'show_edit' not in st.session_state:
    st.session_state.show_edit = False

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")
st.caption("A daily pet care planner that schedules, sorts, and checks for conflicts.")

# ── Owner & Pet setup ──────────────────────────────────────────────────────────
st.subheader("Owner & Pet Setup")

col1, col2 = st.columns(2)
with col1:
    owner_name = st.text_input("Owner name", value="Jordan")
with col2:
    budget = st.slider("Daily time budget (minutes)", min_value=30, max_value=480, value=120, step=15)

col3, col4 = st.columns(2)
with col3:
    pet_name = st.text_input("Pet name", value="Mochi")
with col4:
    species = st.selectbox("Species", ["dog", "cat", "other"])

if st.button("Create Pet"):
    existing_names = [p.name for p in st.session_state.owner.pets] if st.session_state.owner else []
    if pet_name in existing_names:
        st.error(f"A pet named '{pet_name}' already exists. Use a unique name.")
    else:
        pet = Pet(name=pet_name, species=species, age=1, needs={}, tasks=[])
        if st.session_state.owner:
            st.session_state.owner.pets.append(pet)
            st.session_state.owner.available_minutes_per_day = budget
            st.session_state.scheduler = Scheduler(st.session_state.owner)
            st.success(f"Pet {pet_name} added!")
        else:
            st.session_state.owner = Owner(
                name=owner_name,
                available_minutes_per_day=budget,
                preferences={},
                constraints=[],
                pets=[pet],
            )
            st.session_state.scheduler = Scheduler(st.session_state.owner)
            st.success(f"Owner {owner_name} and pet {pet_name} created!")

if st.session_state.owner:
    st.dataframe(
        [{"Name": p.name, "Species": p.species} for p in st.session_state.owner.pets],
        width="100%",
    )

st.divider()

# ── Add Task ───────────────────────────────────────────────────────────────────
st.subheader("Add Task")

col1, col2, col3 = st.columns(3)
with col1:
    task_title = st.text_input("Task title", value="Morning walk")
with col2:
    duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
with col3:
    priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)

col4, col5, col6 = st.columns(3)
with col4:
    required = st.checkbox("Required?", value=True)
with col5:
    frequency = st.selectbox("Frequency", ["daily", "weekly", "once"])
with col6:
    start_time_input = st.text_input("Start time (HH:MM, optional)", value="")

if st.session_state.owner:
    pet_names = [p.name for p in st.session_state.owner.pets]
    assign_to = st.selectbox("Assign to pet", pet_names) if pet_names else None
else:
    assign_to = None

if st.button("Add task"):
    if not st.session_state.scheduler:
        st.error("Create a pet first.")
    else:
        priority_map = {"low": 1, "medium": 3, "high": 5}
        existing = st.session_state.owner.get_all_tasks()
        start_time = start_time_input.strip() if start_time_input.strip() else None
        task = Task(
            id=f"task-{len(existing) + 1}",
            description=task_title,
            type="general",
            duration_minutes=int(duration),
            priority=priority_map[priority],
            required=required,
            frequency=frequency,
            completion_status=False,
            start_time=start_time,
        )
        st.session_state.scheduler.add_task(task, assign_to)
        st.success(f"'{task_title}' added for {assign_to}!")

# Task list with mark-complete
if st.session_state.scheduler:
    all_tasks = st.session_state.owner.get_all_tasks()
    if all_tasks:
        st.markdown("**All tasks:**")
        st.dataframe(
            [
                {
                    "Task": t.description,
                    "Pet": next((p.name for p in st.session_state.owner.pets if t in p.tasks), "—"),
                    "Duration (min)": t.duration_minutes,
                    "Priority": t.priority,
                    "Required": "Yes" if t.required else "No",
                    "Frequency": t.frequency,
                    "Start time": t.start_time or "—",
                    "Done": "✓" if t.completion_status else "",
                }
                for t in all_tasks
            ],
            width="100%",
        )

        incomplete_tasks = [t for t in all_tasks if not t.completion_status]
        if incomplete_tasks:
            selected_task = st.selectbox(
                "Mark task complete",
                incomplete_tasks,
                format_func=lambda t: t.description,
            )
            if st.button("Mark complete"):
                next_task = st.session_state.scheduler.mark_task_complete(selected_task.id)
                if next_task:
                    st.success(f"Done! Next occurrence scheduled for {next_task.due_date}.")
                else:
                    st.success("Task marked complete.")

        if st.button("Edit a task" if not st.session_state.show_edit else "Close editor"):
            st.session_state.show_edit = not st.session_state.show_edit

        if st.session_state.show_edit:
            edit_id = st.selectbox("Select task to edit", [t.id for t in all_tasks], key="edit_select")
            task_to_edit = next(t for t in all_tasks if t.id == edit_id)

            priority_reverse = {1: "low", 3: "medium", 5: "high"}
            e_col1, e_col2, e_col3 = st.columns(3)
            with e_col1:
                e_title = st.text_input("Title", value=task_to_edit.description, key="e_title")
            with e_col2:
                e_duration = st.number_input("Duration (min)", min_value=1, max_value=240,
                                             value=task_to_edit.duration_minutes, key="e_duration")
            with e_col3:
                e_priority = st.selectbox("Priority", ["low", "medium", "high"],
                                          index=["low", "medium", "high"].index(
                                              priority_reverse.get(task_to_edit.priority, "medium")
                                          ), key="e_priority")

            e_col4, e_col5, e_col6 = st.columns(3)
            with e_col4:
                e_required = st.checkbox("Required?", value=task_to_edit.required, key="e_required")
            with e_col5:
                e_frequency = st.selectbox("Frequency", ["daily", "weekly", "once"],
                                           index=["daily", "weekly", "once"].index(task_to_edit.frequency),
                                           key="e_frequency")
            with e_col6:
                e_start = st.text_input("Start time (HH:MM)", value=task_to_edit.start_time or "",
                                        key="e_start")

            if st.button("Save changes"):
                priority_map = {"low": 1, "medium": 3, "high": 5}
                task_to_edit.description = e_title
                task_to_edit.duration_minutes = int(e_duration)
                task_to_edit.set_priority(priority_map[e_priority])
                task_to_edit.required = e_required
                task_to_edit.frequency = e_frequency
                task_to_edit.start_time = e_start.strip() if e_start.strip() else None
                st.session_state.scheduler._invalidate_cache()
                st.success(f"Task '{e_title}' updated!")
                st.rerun()
    else:
        st.info("No tasks yet. Add one above.")

st.divider()

# ── Generate Schedule ──────────────────────────────────────────────────────────
st.subheader("Today's Schedule")

if st.button("Generate schedule"):
    if not st.session_state.scheduler:
        st.error("Create a pet first.")
    else:
        scheduler = st.session_state.scheduler
        scheduled, skipped = scheduler.generate_plan()

        if scheduled:
            sorted_tasks = scheduler.sort_by_time(scheduled)
            total_min = sum(t.duration_minutes for t in sorted_tasks)
            budget_used = st.session_state.owner.available_minutes_per_day
            st.success(
                f"{len(sorted_tasks)} task(s) scheduled — "
                f"{total_min} of {budget_used} minutes used."
            )
            task_to_pet = {
                t.id: p.name
                for p in st.session_state.owner.pets
                for t in p.tasks
            }
            st.table(
                [
                    {
                        "Time": t.start_time or "—",
                        "Task": t.description,
                        "Pet": task_to_pet.get(t.id, "—"),
                        "Duration (min)": t.duration_minutes,
                        "Priority": t.priority,
                        "Required": "Yes" if t.required else "No",
                    }
                    for t in sorted_tasks
                ]
            )
        else:
            st.warning("No tasks could be scheduled. Add tasks or increase your time budget.")

        if skipped:
            with st.expander(f"Skipped — did not fit ({len(skipped)} task(s))"):
                for t in skipped:
                    st.write(f"- **{t.description}** — {t.duration_minutes} min, priority {t.priority}")

        # ── Conflict check ─────────────────────────────────────────────────────
        st.markdown("#### Conflict Check")
        warnings = scheduler.detect_conflicts()
        conflicts = [w for w in warnings if w.startswith("CONFLICT")]
        notices   = [w for w in warnings if w.startswith("WARNING")]

        if conflicts:
            for msg in conflicts:
                # Parse scope label for a friendlier header
                scope = "same pet" if "same pet" in msg else "different pets"
                st.warning(
                    f"**Time overlap detected ({scope})**\n\n"
                    f"{msg}\n\n"
                    f"*Fix: adjust the start time of one of these tasks so they no longer overlap.*"
                )
        if notices:
            for msg in notices:
                st.info(
                    f"**Missing start time** — {msg}\n\n"
                    f"*Add a start time to this task to enable full conflict checking.*"
                )
        if not conflicts and not notices:
            st.success("No conflicts detected — your schedule looks good!")

st.divider()

# ── Ask PawPal AI ──────────────────────────────────────────────────────────────
st.subheader("Ask PawPal AI")
st.caption(
    "Ask any pet care question. The AI retrieves relevant knowledge and personalizes "
    "its answer using your actual pets and current schedule."
)

_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

if not _api_key:
    st.warning(
        "**ANTHROPIC_API_KEY not set.** Create a `.env` file in the project root:\n\n"
        "```\nANTHROPIC_API_KEY=your_key_here\n```\n\n"
        "Get a free key at [console.anthropic.com](https://console.anthropic.com)."
    )
else:
    ai_question = st.text_input(
        "Ask PawPal AI",
        placeholder="e.g. How much exercise does my dog need? What tasks should I add for my cat?",
        label_visibility="collapsed",
    )

    if st.button("Ask AI", disabled=not bool(ai_question.strip())):
        rag = get_rag_engine()
        pet_context = build_pet_context(
            st.session_state.get("owner"),
            st.session_state.get("scheduler"),
        )

        retrieved_chunks = rag.retrieve(ai_question)

        with st.expander("Knowledge sources retrieved", expanded=False):
            if retrieved_chunks:
                for chunk in retrieved_chunks:
                    colon = chunk.find(":")
                    topic = chunk[:colon] if colon > 0 else "Tip"
                    preview = chunk[colon + 1:].strip()[:130] if colon > 0 else chunk[:130]
                    st.markdown(f"**{topic}** — {preview}…")
            else:
                st.write("No closely matching entries found in the knowledge base.")

        st.markdown("**PawPal AI:**")
        response_container = st.empty()
        full_response = ""

        try:
            for token in rag.stream_answer(
                ai_question, pet_context, _api_key, retrieved_chunks
            ):
                full_response += token
                response_container.markdown(full_response + "▌")
            response_container.markdown(full_response)
        except ValueError as exc:
            response_container.error(str(exc))
