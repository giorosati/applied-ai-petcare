from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

@dataclass
class Pet:
    name: str
    species: str
    age: int
    needs: Dict[str, str]
    tasks: List['Task']

    def add_need(self, type: str, detail: str):
        """Add a need to the pet's needs dictionary."""
        self.needs[type] = detail

    def is_med_required(self) -> bool:
        """Check if the pet requires medication."""
        return "medication" in self.needs or any("med" in need.lower() for need in self.needs.values())

@dataclass
class Task:
    id: str
    description: str
    type: str
    duration_minutes: int
    priority: int
    required: bool
    frequency: str  # e.g., "daily", "weekly"
    completion_status: bool  # True if completed
    start_time: Optional[str] = None  # preferred start time in "HH:MM" format, e.g. "08:30"
    due_date: Optional[date] = None   # date this occurrence is due

    def update_status(self, new_status: bool):
        """Update the completion status of the task."""
        self.completion_status = new_status

    def set_priority(self, level: int):
        """Set the priority level of the task, clamped between 1 and 5."""
        # Improvement #6: clamp to valid range so out-of-range values don't distort sort order
        self.priority = max(1, min(5, level))

class Owner:
    def __init__(self, name: str, available_minutes_per_day: int, preferences: Dict[str, str], constraints: List[str], pets: List[Pet]):
        """Create an Owner with a daily time budget and a list of pets.

        Args:
            name: The owner's display name.
            available_minutes_per_day: Total minutes the owner can spend on
                pet care each day. Used as the scheduler's hard time ceiling.
            preferences: Free-form key/value pairs describing scheduling
                preferences (e.g. {"morning": "preferred"}).
            constraints: Plain-text constraints noted for the owner
                (e.g. ["no evening tasks"]).
            pets: The pets this owner is responsible for. Every element must
                be a Pet instance.

        Raises:
            ValueError: If any element of pets is not a Pet instance.
        """
        for pet in pets:
            if not isinstance(pet, Pet):
                raise ValueError("All pets must be Pet instances")
        self.name = name
        self.available_minutes_per_day = available_minutes_per_day
        self.preferences = preferences
        self.constraints = constraints
        self.pets = pets

    def get_all_tasks(self) -> List[Task]:
        """Retrieve all tasks from all pets, deduplicated by task ID.

        Returns:
            A flat list of Task objects across every pet. If the same task ID
            appears on more than one pet, only the first occurrence is kept,
            preventing a task from being double-scheduled.
        """
        # Improvement #3: deduplicate by ID to prevent double-scheduling
        seen_ids = set()
        all_tasks = []
        for pet in self.pets:
            for task in pet.tasks:
                if task.id not in seen_ids:
                    seen_ids.add(task.id)
                    all_tasks.append(task)
        return all_tasks

    def set_availability(self, start: str, end: str):
        """Set available_minutes_per_day from a start and end clock time.

        Args:
            start: The beginning of the owner's available window in "HH:MM"
                format (e.g. "08:00").
            end: The end of the available window in "HH:MM" format
                (e.g. "20:00"). Must be later in the day than start.
        """
        # Improvement #7: actually compute available minutes from time strings
        start_h, start_m = map(int, start.split(":"))
        end_h, end_m = map(int, end.split(":"))
        self.available_minutes_per_day = (end_h * 60 + end_m) - (start_h * 60 + start_m)

    def add_preference(self, key: str, value: str):
        """Add a preference to the owner's preferences."""
        self.preferences[key] = value

class Scheduler:
    def __init__(self, owner: Owner):
        """Create a Scheduler for the given owner.

        The scheduler caches the generated plan and only recomputes it when
        tasks are added, removed, or marked complete (_dirty flag).

        Args:
            owner: The Owner whose pets and time budget drive scheduling.

        Raises:
            ValueError: If owner is not an Owner instance.
        """
        if not isinstance(owner, Owner):
            raise ValueError("owner must be an Owner instance")
        self.owner = owner
        self._plan_cache: Optional[Tuple[List[Task], List[Task]]] = None
        self._dirty = True

    def _invalidate_cache(self):
        """Mark the cached plan stale so the next access recomputes it."""
        self._dirty = True

    @property
    def planned_tasks(self) -> List[Task]:
        """Return only the scheduled tasks (cached)."""
        return self._get_plan()[0]

    def _get_plan(self) -> Tuple[List[Task], List[Task]]:
        """Return (scheduled, skipped), recomputing only when data has changed."""
        if not self._dirty and self._plan_cache is not None:
            return self._plan_cache
        self._plan_cache = self.generate_plan()
        self._dirty = False
        return self._plan_cache

    def generate_plan(self) -> Tuple[List[Task], List[Task]]:
        """Generate a prioritized daily plan within the owner's time budget.

        Only tasks with frequency "daily" and completion_status False are
        considered. Tasks are sorted by (required desc, priority desc) so
        required tasks always claim slots before optional ones. The loop
        uses a bin-packing strategy — it never stops early on a task that
        doesn't fit, so smaller lower-priority tasks can still fill leftover
        minutes after a large task is skipped.

        Returns:
            A tuple of (scheduled_tasks, skipped_tasks) where:
            - scheduled_tasks: Tasks that fit within available_minutes_per_day,
              in the order they were selected.
            - skipped_tasks: Daily incomplete tasks that did not fit in the
              budget, useful for surfacing to the owner as unscheduled.
        """
        budget = self.owner.available_minutes_per_day

        daily_tasks = [
            t for t in self.owner.get_all_tasks()
            if t.frequency == "daily"
            and (t.due_date is None or t.due_date <= date.today())
        ]
        candidates  = sorted(
            daily_tasks,
            key=lambda t: (-int(t.required), int(t.completion_status), -t.priority),
        )

        scheduled_ids: set = set()
        plan: List[Task] = []
        total_time = 0

        for task in candidates:
            if task.completion_status:
                continue
            if total_time + task.duration_minutes <= budget:
                plan.append(task)
                scheduled_ids.add(task.id)
                total_time += task.duration_minutes

        skipped = [t for t in daily_tasks if t.id not in scheduled_ids and not t.completion_status]
        return plan, skipped

    def apply_constraints(self):
        """Apply additional constraints to the plan."""
        pass

    def filter_tasks(
        self,
        pet_name: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> List[Task]:
        """Return tasks filtered by pet name and/or completion status.

        Both parameters are optional. Omitting both returns every task across
        all pets. When both are supplied, a task must satisfy both conditions
        (AND logic) to be included.

        Args:
            pet_name: If provided, only tasks belonging to the pet with this
                exact name are returned. Non-matching pets are skipped in
                full before their tasks are iterated, which is slightly more
                efficient than post-filtering the flat task list.
            completed: If True, return only tasks where completion_status is
                True. If False, return only incomplete tasks. If None (the
                default), completion status is ignored.

        Returns:
            A list of Task objects that match all supplied filters, preserving
            the order in which tasks appear on each pet.
        """
        results: List[Task] = []
        for pet in self.owner.pets:
            if pet_name is not None and pet.name != pet_name:
                continue
            for task in pet.tasks:
                if completed is not None and task.completion_status != completed:
                    continue
                results.append(task)
        return results

    def detect_conflicts(self) -> List[str]:
        """Check the scheduled plan for time-window overlaps between tasks.

        Uses the standard interval-overlap test for every pair of timed tasks:
            A.start < B.end  AND  B.start < A.end
        This correctly catches partial overlaps, full containment, and tasks
        that share an exact start time. Conflicts are reported for both same-pet
        and cross-pet pairs so the owner can reschedule either.

        Tasks without a start_time cannot be checked and produce a WARNING
        entry instead of a CONFLICT entry. The method never raises an exception
        so the caller can always handle warnings gracefully.

        Returns:
            A list of human-readable warning strings. Each string is prefixed
            with either "CONFLICT" (overlap detected) or "WARNING" (task could
            not be checked). An empty list means the schedule is conflict-free.
        """
        def to_minutes(hhmm: str) -> int:
            h, m = hhmm.split(":")
            return int(h) * 60 + int(m)

        # Build a flat list of (task, pet_name) for all scheduled tasks
        scheduled = self._get_plan()[0]

        task_to_pet: Dict[str, str] = {}
        for pet in self.owner.pets:
            for task in pet.tasks:
                task_to_pet[task.id] = pet.name

        timed   = [(t, task_to_pet.get(t.id, "Unknown")) for t in scheduled if t.start_time]
        untimed = [(t, task_to_pet.get(t.id, "Unknown")) for t in scheduled if not t.start_time]

        warnings: List[str] = []

        # Note any scheduled tasks we cannot check
        for task, pet_name in untimed:
            warnings.append(
                f"WARNING: '{task.description}' ({pet_name}) has no start_time "
                f"and cannot be checked for conflicts."
            )

        # Check every pair of timed tasks for overlap
        for i in range(len(timed)):
            for j in range(i + 1, len(timed)):
                task_a, pet_a = timed[i]
                task_b, pet_b = timed[j]

                a_start = to_minutes(task_a.start_time)
                a_end   = a_start + task_a.duration_minutes
                b_start = to_minutes(task_b.start_time)
                b_end   = b_start + task_b.duration_minutes

                if a_start < b_end and b_start < a_end:
                    scope = "same pet" if pet_a == pet_b else "different pets"
                    warnings.append(
                        f"CONFLICT ({scope}): '{task_a.description}' ({pet_a}, "
                        f"{task_a.start_time}->{a_end // 60:02d}:{a_end % 60:02d}) "
                        f"overlaps '{task_b.description}' ({pet_b}, "
                        f"{task_b.start_time}->{b_end // 60:02d}:{b_end % 60:02d})"
                    )

        return warnings

    def sort_by_time(self, tasks: List[Task]) -> List[Task]:
        """Return a new list of tasks sorted by start_time in ascending order.

        "HH:MM" strings are converted to total minutes since midnight before
        comparing (e.g. "09:00" -> 540, "13:30" -> 810). This avoids the
        lexicographic pitfall where "9:00" would sort after "13:30" as a
        plain string comparison. Tasks with no start_time receive a sentinel
        value of 1440 (24 * 60) so they always appear after timed tasks.

        Args:
            tasks: The list of Task objects to sort. The original list is not
                modified; a new sorted list is returned.

        Returns:
            A new list of Task objects ordered from earliest start_time to
            latest, with untimed tasks grouped at the end.
        """
        def time_key(task: Task) -> int:
            if task.start_time is None:
                return 24 * 60  # sort tasks with no time after all timed ones
            h, m = task.start_time.split(":")
            return int(h) * 60 + int(m)

        return sorted(tasks, key=lambda t: time_key(t))

    def explain_plan(self) -> str:
        """Provide a string explanation of the generated plan."""
        scheduled, skipped = self._get_plan()

        # Build a fast task-id → pet-name lookup
        task_to_pet: Dict[str, str] = {}
        for pet in self.owner.pets:
            for task in pet.tasks:
                task_to_pet[task.id] = pet.name

        if not scheduled:
            explanation = "No tasks can be scheduled within available time.\n"
        else:
            explanation = "Scheduled tasks (prioritized):\n"
            for task in scheduled:
                pet_name = task_to_pet.get(task.id, "Unknown")
                explanation += (
                    f"- {task.description} for {pet_name} "
                    f"({task.duration_minutes} min, priority {task.priority})\n"
                )

        # Improvement #10: show what didn't make it and why
        if skipped:
            explanation += "\nCould not schedule (insufficient time):\n"
            for task in skipped:
                pet_name = task_to_pet.get(task.id, "Unknown")
                explanation += (
                    f"- {task.description} for {pet_name} "
                    f"({task.duration_minutes} min, priority {task.priority})\n"
                )

        return explanation

    def add_task(self, task: Task, pet_name: str):
        """Add a task to a specific pet."""
        for pet in self.owner.pets:
            if pet.name == pet_name:
                pet.tasks.append(task)
                self._invalidate_cache()
                break

    def remove_task(self, task_id: str):
        """Remove a task by ID from all pets."""
        for pet in self.owner.pets:
            pet.tasks = [t for t in pet.tasks if t.id != task_id]
        self._invalidate_cache()

    def mark_task_complete(self, task_id: str) -> Optional[Task]:
        """Mark a task complete and auto-schedule its next recurrence.

        Sets completion_status to True on the target task, then — if the task
        has a recurring frequency — creates a fresh Task copy with
        completion_status False and a due_date computed via timedelta:
            "daily"  -> today + timedelta(days=1)
            "weekly" -> today + timedelta(weeks=1)
        timedelta handles month and year rollovers automatically, so no
        manual calendar arithmetic is required. The new task is appended to
        the same pet's task list and the plan cache is invalidated.

        Args:
            task_id: The id of the task to mark complete. Must match an
                existing task on one of the owner's pets.

        Returns:
            The newly created Task representing the next occurrence, or None
            if the task's frequency is not "daily" or "weekly".

        Raises:
            ValueError: If no task with the given task_id is found across any
                of the owner's pets.
        """
        RECURRENCE_DELTA = {
            "daily":  timedelta(days=1),
            "weekly": timedelta(weeks=1),
        }

        target_task: Optional[Task] = None
        target_pet:  Optional[Pet]  = None

        for pet in self.owner.pets:
            for task in pet.tasks:
                if task.id == task_id:
                    target_task = task
                    target_pet  = pet
                    break
            if target_task:
                break

        if target_task is None:
            raise ValueError(f"No task with id '{task_id}' found.")

        target_task.update_status(True)
        self._invalidate_cache()

        delta = RECURRENCE_DELTA.get(target_task.frequency)
        if delta is None:
            return None  # not a recurring frequency — nothing more to do

        next_due = date.today() + delta
        next_task = Task(
            id=f"{target_task.id}-{next_due.isoformat()}",
            description=target_task.description,
            type=target_task.type,
            duration_minutes=target_task.duration_minutes,
            priority=target_task.priority,
            required=target_task.required,
            frequency=target_task.frequency,
            completion_status=False,
            start_time=target_task.start_time,
            due_date=next_due,
        )
        target_pet.tasks.append(next_task)
        self._invalidate_cache()
        return next_task
