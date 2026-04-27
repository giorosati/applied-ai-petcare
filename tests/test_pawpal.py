import pytest
from pawpal_system import Task, Pet, Owner, Scheduler

def test_task_completion():
    """Verify that calling update_status(True) changes the task's completion_status to True."""
    task = Task(
        id="test1",
        description="Test task",
        type="test",
        duration_minutes=10,
        priority=3,
        required=False,
        frequency="daily",
        completion_status=False
    )
    assert not task.completion_status
    task.update_status(True)
    assert task.completion_status

def test_task_addition():
    """Verify that adding a task to a Pet increases that pet's task count."""
    pet = Pet(
        name="TestPet",
        species="Dog",
        age=2,
        needs={},
        tasks=[]
    )
    owner = Owner(
        name="TestOwner",
        available_minutes_per_day=60,
        preferences={},
        constraints=[],
        pets=[pet]
    )
    scheduler = Scheduler(owner)
    initial_count = len(pet.tasks)
    task = Task(
        id="new_task",
        description="New task",
        type="test",
        duration_minutes=5,
        priority=2,
        required=False,
        frequency="daily",
        completion_status=False
    )
    scheduler.add_task(task, pet.name)
    assert len(pet.tasks) == initial_count + 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_task(id, description, duration, priority, required=False,
              frequency="daily", completed=False, start_time=None):
    return Task(
        id=id,
        description=description,
        type="test",
        duration_minutes=duration,
        priority=priority,
        required=required,
        frequency=frequency,
        completion_status=completed,
        start_time=start_time,
    )


def make_scheduler(tasks, budget=120):
    pet = Pet(name="Rex", species="Dog", age=3, needs={}, tasks=tasks)
    owner = Owner(name="Alex", available_minutes_per_day=budget,
                  preferences={}, constraints=[], pets=[pet])
    return Scheduler(owner)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_schedule_all_tasks_fit():
    """All tasks fit within the budget — none are skipped."""
    tasks = [
        make_task("t1", "Walk",  30, priority=3),
        make_task("t2", "Feed",  20, priority=2),
    ]
    scheduler = make_scheduler(tasks, budget=60)
    scheduled, skipped = scheduler.generate_plan()
    assert len(scheduled) == 2
    assert skipped == []


def test_required_tasks_scheduled_before_optional():
    """Required tasks consume budget before optional ones."""
    tasks = [
        make_task("t1", "Optional play",  50, priority=5, required=False),
        make_task("t2", "Required meds",  50, priority=1, required=True),
    ]
    # Budget fits exactly one 50-min task
    scheduler = make_scheduler(tasks, budget=50)
    scheduled, skipped = scheduler.generate_plan()
    assert len(scheduled) == 1
    assert scheduled[0].id == "t2"
    assert len(skipped) == 1
    assert skipped[0].id == "t1"


def test_explain_plan_lists_scheduled_and_skipped():
    """explain_plan output mentions both scheduled and skipped tasks."""
    tasks = [
        make_task("t1", "Walk",  30, priority=3),
        make_task("t2", "Bath",  120, priority=2),
    ]
    scheduler = make_scheduler(tasks, budget=60)
    explanation = scheduler.explain_plan()
    assert "Walk" in explanation
    assert "Bath" in explanation
    assert "Could not schedule" in explanation


# ---------------------------------------------------------------------------
# Sorting correctness
# ---------------------------------------------------------------------------

def test_sort_by_time_chronological_order():
    """Tasks are returned sorted earliest to latest start_time."""
    tasks = [
        make_task("t1", "Afternoon walk",  30, priority=1, start_time="13:00"),
        make_task("t2", "Morning feed",    20, priority=1, start_time="08:00"),
        make_task("t3", "Mid-morning med", 15, priority=1, start_time="09:30"),
    ]
    scheduler = make_scheduler(tasks)
    sorted_tasks = scheduler.sort_by_time(tasks)
    times = [t.start_time for t in sorted_tasks]
    assert times == ["08:00", "09:30", "13:00"]


def test_sort_by_time_untimed_tasks_go_last():
    """Tasks without start_time are placed after all timed tasks."""
    tasks = [
        make_task("t1", "Untimed grooming", 20, priority=1, start_time=None),
        make_task("t2", "Morning feed",     20, priority=1, start_time="08:00"),
    ]
    scheduler = make_scheduler(tasks)
    sorted_tasks = scheduler.sort_by_time(tasks)
    assert sorted_tasks[0].start_time == "08:00"
    assert sorted_tasks[1].start_time is None


# ---------------------------------------------------------------------------
# Recurrence logic
# ---------------------------------------------------------------------------

def test_mark_daily_task_complete_creates_next_occurrence():
    """Completing a daily task creates a new task due the following day."""
    from datetime import date, timedelta
    task = make_task("t1", "Walk", 30, priority=3, frequency="daily")
    scheduler = make_scheduler([task])
    next_task = scheduler.mark_task_complete("t1")

    assert next_task is not None
    assert next_task.completion_status is False
    assert next_task.due_date == date.today() + timedelta(days=1)


def test_mark_weekly_task_complete_creates_next_occurrence():
    """Completing a weekly task creates a new task due seven days later."""
    from datetime import date, timedelta
    task = make_task("t1", "Vet checkup", 60, priority=4, frequency="weekly")
    scheduler = make_scheduler([task])
    next_task = scheduler.mark_task_complete("t1")

    assert next_task is not None
    assert next_task.due_date == date.today() + timedelta(weeks=1)


def test_mark_nonrecurring_task_complete_returns_none():
    """Completing a one-off task returns None (no recurrence created)."""
    task = make_task("t1", "One-time bath", 30, priority=2, frequency="once")
    scheduler = make_scheduler([task])
    result = scheduler.mark_task_complete("t1")
    assert result is None


def test_mark_complete_unknown_id_raises():
    """mark_task_complete raises ValueError for an unknown task ID."""
    scheduler = make_scheduler([])
    with pytest.raises(ValueError):
        scheduler.mark_task_complete("nonexistent")


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def test_detect_conflicts_same_start_time():
    """Two tasks starting at the same time are flagged as a CONFLICT."""
    tasks = [
        make_task("t1", "Walk",  30, priority=3, start_time="09:00"),
        make_task("t2", "Feed",  20, priority=2, start_time="09:00"),
    ]
    scheduler = make_scheduler(tasks, budget=120)
    warnings = scheduler.detect_conflicts()
    assert any("CONFLICT" in w for w in warnings)


def test_detect_conflicts_partial_overlap():
    """A task that starts before another ends is flagged as a CONFLICT."""
    tasks = [
        make_task("t1", "Walk",  60, priority=3, start_time="09:00"),  # 09:00–10:00
        make_task("t2", "Feed",  30, priority=2, start_time="09:30"),  # 09:30–10:00
    ]
    scheduler = make_scheduler(tasks, budget=120)
    warnings = scheduler.detect_conflicts()
    assert any("CONFLICT" in w for w in warnings)


def test_no_conflict_when_tasks_are_adjacent():
    """A task ending exactly when the next one starts is NOT a conflict."""
    tasks = [
        make_task("t1", "Walk",  60, priority=3, start_time="08:00"),  # 08:00–09:00
        make_task("t2", "Feed",  30, priority=2, start_time="09:00"),  # 09:00–09:30
    ]
    scheduler = make_scheduler(tasks, budget=120)
    warnings = scheduler.detect_conflicts()
    assert not any("CONFLICT" in w for w in warnings)


def test_detect_conflicts_warning_for_untimed_task():
    """A scheduled task without start_time produces a WARNING entry."""
    tasks = [
        make_task("t1", "Untimed grooming", 30, priority=2, start_time=None),
    ]
    scheduler = make_scheduler(tasks, budget=120)
    warnings = scheduler.detect_conflicts()
    assert any("WARNING" in w for w in warnings)


def test_no_conflicts_clean_schedule():
    """Non-overlapping timed tasks return an empty conflict list."""
    tasks = [
        make_task("t1", "Walk",  30, priority=3, start_time="08:00"),  # 08:00–08:30
        make_task("t2", "Feed",  20, priority=2, start_time="09:00"),  # 09:00–09:20
    ]
    scheduler = make_scheduler(tasks, budget=120)
    assert scheduler.detect_conflicts() == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_pet_with_no_tasks_produces_empty_plan():
    """An owner whose pet has zero tasks results in an empty schedule."""
    scheduler = make_scheduler([], budget=120)
    scheduled, skipped = scheduler.generate_plan()
    assert scheduled == []
    assert skipped == []


def test_zero_budget_skips_all_tasks():
    """With 0 available minutes every task lands in skipped."""
    tasks = [make_task("t1", "Walk", 30, priority=3)]
    scheduler = make_scheduler(tasks, budget=0)
    scheduled, skipped = scheduler.generate_plan()
    assert scheduled == []
    assert len(skipped) == 1


def test_task_duration_exactly_equals_budget():
    """A single task whose duration equals the budget is scheduled, not skipped."""
    tasks = [make_task("t1", "Long walk", 60, priority=3)]
    scheduler = make_scheduler(tasks, budget=60)
    scheduled, skipped = scheduler.generate_plan()
    assert len(scheduled) == 1
    assert skipped == []


def test_duplicate_task_ids_deduplicated():
    """The same task ID on two pets is only scheduled once."""
    shared_task_id = "shared"
    pet1 = Pet(name="Rex",   species="Dog", age=3, needs={},
               tasks=[make_task(shared_task_id, "Walk", 30, priority=3)])
    pet2 = Pet(name="Bella", species="Cat", age=2, needs={},
               tasks=[make_task(shared_task_id, "Walk", 30, priority=3)])
    owner = Owner(name="Alex", available_minutes_per_day=120,
                  preferences={}, constraints=[], pets=[pet1, pet2])
    all_tasks = owner.get_all_tasks()
    ids = [t.id for t in all_tasks]
    assert ids.count(shared_task_id) == 1


def test_cache_invalidated_after_add_task():
    """planned_tasks reflects a newly added task after add_task is called."""
    scheduler = make_scheduler([], budget=120)
    assert scheduler.planned_tasks == []

    new_task = make_task("t1", "Walk", 30, priority=3)
    scheduler.add_task(new_task, "Rex")
    assert any(t.id == "t1" for t in scheduler.planned_tasks)


# ---------------------------------------------------------------------------
# Task.set_priority – clamping
# ---------------------------------------------------------------------------

def test_set_priority_clamps_below_minimum():
    """Priority below 1 is clamped to 1."""
    task = make_task("t1", "Walk", 30, priority=3)
    task.set_priority(0)
    assert task.priority == 1


def test_set_priority_clamps_above_maximum():
    """Priority above 5 is clamped to 5."""
    task = make_task("t1", "Walk", 30, priority=3)
    task.set_priority(9)
    assert task.priority == 5


def test_set_priority_valid_value_unchanged():
    """A priority within range is stored as-is."""
    task = make_task("t1", "Walk", 30, priority=3)
    task.set_priority(4)
    assert task.priority == 4


# ---------------------------------------------------------------------------
# Pet.is_med_required
# ---------------------------------------------------------------------------

def test_is_med_required_true_with_medication_key():
    """Returns True when needs contains the key 'medication'."""
    pet = Pet(name="Rex", species="Dog", age=3, needs={"medication": "insulin"}, tasks=[])
    assert pet.is_med_required() is True


def test_is_med_required_true_with_med_in_value():
    """Returns True when a need value contains the substring 'med'."""
    pet = Pet(name="Rex", species="Dog", age=3, needs={"health": "daily meds needed"}, tasks=[])
    assert pet.is_med_required() is True


def test_is_med_required_false_without_medication():
    """Returns False when no medication-related need is present."""
    pet = Pet(name="Rex", species="Dog", age=3, needs={"food": "kibble"}, tasks=[])
    assert pet.is_med_required() is False


def test_is_med_required_false_empty_needs():
    """Returns False when needs dict is empty."""
    pet = Pet(name="Rex", species="Dog", age=3, needs={}, tasks=[])
    assert pet.is_med_required() is False


# ---------------------------------------------------------------------------
# Owner.set_availability
# ---------------------------------------------------------------------------

def test_set_availability_computes_minutes():
    """08:00 to 20:00 is 720 available minutes."""
    pet = Pet(name="Rex", species="Dog", age=3, needs={}, tasks=[])
    owner = Owner(name="Alex", available_minutes_per_day=60,
                  preferences={}, constraints=[], pets=[pet])
    owner.set_availability("08:00", "20:00")
    assert owner.available_minutes_per_day == 720


def test_set_availability_short_window():
    """09:00 to 09:30 is 30 available minutes."""
    pet = Pet(name="Rex", species="Dog", age=3, needs={}, tasks=[])
    owner = Owner(name="Alex", available_minutes_per_day=60,
                  preferences={}, constraints=[], pets=[pet])
    owner.set_availability("09:00", "09:30")
    assert owner.available_minutes_per_day == 30


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

def test_owner_init_raises_for_non_pet():
    """Owner raises ValueError when pets list contains a non-Pet object."""
    with pytest.raises(ValueError):
        Owner(name="Alex", available_minutes_per_day=60,
              preferences={}, constraints=[], pets=["not a pet"])


def test_scheduler_init_raises_for_non_owner():
    """Scheduler raises ValueError when passed something that isn't an Owner."""
    with pytest.raises(ValueError):
        Scheduler("not an owner")


# ---------------------------------------------------------------------------
# Scheduler.remove_task
# ---------------------------------------------------------------------------

def test_remove_task_removes_from_pet():
    """After remove_task the task no longer appears on the pet."""
    tasks = [make_task("t1", "Walk", 30, priority=3)]
    scheduler = make_scheduler(tasks, budget=120)
    scheduler.remove_task("t1")
    assert all(t.id != "t1" for t in scheduler.owner.pets[0].tasks)


def test_remove_task_invalidates_cache():
    """remove_task marks the plan cache dirty."""
    tasks = [make_task("t1", "Walk", 30, priority=3)]
    scheduler = make_scheduler(tasks, budget=120)
    _ = scheduler.planned_tasks  # populate cache
    scheduler.remove_task("t1")
    assert scheduler._dirty is True


def test_remove_task_nonexistent_id_does_not_raise():
    """remove_task with an unknown ID silently does nothing."""
    scheduler = make_scheduler([], budget=120)
    scheduler.remove_task("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# Scheduler.filter_tasks
# ---------------------------------------------------------------------------

def test_filter_tasks_by_pet_name():
    """filter_tasks(pet_name=...) returns only that pet's tasks."""
    pet1 = Pet(name="Rex",   species="Dog", age=3, needs={},
               tasks=[make_task("t1", "Walk", 30, priority=3)])
    pet2 = Pet(name="Bella", species="Cat", age=2, needs={},
               tasks=[make_task("t2", "Play", 15, priority=2)])
    owner = Owner(name="Alex", available_minutes_per_day=120,
                  preferences={}, constraints=[], pets=[pet1, pet2])
    scheduler = Scheduler(owner)
    results = scheduler.filter_tasks(pet_name="Rex")
    assert len(results) == 1
    assert results[0].id == "t1"


def test_filter_tasks_by_completion_status():
    """filter_tasks(completed=False/True) splits tasks by completion."""
    tasks = [
        make_task("t1", "Walk", 30, priority=3, completed=False),
        make_task("t2", "Feed", 20, priority=2, completed=True),
    ]
    scheduler = make_scheduler(tasks, budget=120)
    incomplete = scheduler.filter_tasks(completed=False)
    assert all(not t.completion_status for t in incomplete)
    complete = scheduler.filter_tasks(completed=True)
    assert all(t.completion_status for t in complete)


def test_filter_tasks_by_pet_and_completion():
    """filter_tasks with both parameters applies AND logic."""
    pet1 = Pet(name="Rex", species="Dog", age=3, needs={},
               tasks=[
                   make_task("t1", "Walk", 30, priority=3, completed=False),
                   make_task("t2", "Feed", 20, priority=2, completed=True),
               ])
    pet2 = Pet(name="Bella", species="Cat", age=2, needs={},
               tasks=[make_task("t3", "Play", 15, priority=2, completed=False)])
    owner = Owner(name="Alex", available_minutes_per_day=120,
                  preferences={}, constraints=[], pets=[pet1, pet2])
    scheduler = Scheduler(owner)
    results = scheduler.filter_tasks(pet_name="Rex", completed=False)
    assert len(results) == 1
    assert results[0].id == "t1"


# ---------------------------------------------------------------------------
# generate_plan – additional behaviour
# ---------------------------------------------------------------------------

def test_completed_daily_tasks_excluded_from_plan():
    """A completed daily task is not included in the schedule."""
    tasks = [
        make_task("t1", "Walk", 30, priority=3, completed=True),
        make_task("t2", "Feed", 20, priority=2, completed=False),
    ]
    scheduler = make_scheduler(tasks, budget=120)
    scheduled, _ = scheduler.generate_plan()
    ids = [t.id for t in scheduled]
    assert "t1" not in ids
    assert "t2" in ids


def test_weekly_tasks_excluded_from_plan():
    """Weekly tasks are not included in the daily schedule."""
    tasks = [
        make_task("t1", "Weekly bath", 30, priority=3, frequency="weekly"),
        make_task("t2", "Daily feed",  20, priority=2, frequency="daily"),
    ]
    scheduler = make_scheduler(tasks, budget=120)
    scheduled, _ = scheduler.generate_plan()
    ids = [t.id for t in scheduled]
    assert "t1" not in ids
    assert "t2" in ids


def test_once_tasks_excluded_from_plan():
    """One-off tasks are not included in the daily schedule."""
    tasks = [make_task("t1", "One-time vet", 60, priority=5, frequency="once")]
    scheduler = make_scheduler(tasks, budget=120)
    scheduled, _ = scheduler.generate_plan()
    assert scheduled == []


def test_bin_packing_smaller_task_fills_gap():
    """After a large task is skipped, a smaller lower-priority task still fits."""
    tasks = [
        make_task("t1", "Long walk",  90, priority=5),
        make_task("t2", "Quick feed", 30, priority=2),
    ]
    scheduler = make_scheduler(tasks, budget=30)
    scheduled, skipped = scheduler.generate_plan()
    assert any(t.id == "t2" for t in scheduled)
    assert any(t.id == "t1" for t in skipped)


# ---------------------------------------------------------------------------
# Conflict detection – cross-pet scope label
# ---------------------------------------------------------------------------

def test_detect_conflicts_cross_pet_scope_label():
    """Overlapping tasks on different pets include 'different pets' in the message."""
    pet1 = Pet(name="Rex",   species="Dog", age=3, needs={},
               tasks=[make_task("t1", "Walk", 60, priority=3, start_time="09:00")])
    pet2 = Pet(name="Bella", species="Cat", age=2, needs={},
               tasks=[make_task("t2", "Play", 30, priority=2, start_time="09:30")])
    owner = Owner(name="Alex", available_minutes_per_day=120,
                  preferences={}, constraints=[], pets=[pet1, pet2])
    scheduler = Scheduler(owner)
    warnings = scheduler.detect_conflicts()
    assert any("different pets" in w for w in warnings)


# ---------------------------------------------------------------------------
# mark_task_complete – start_time inheritance
# ---------------------------------------------------------------------------

def test_mark_complete_next_occurrence_inherits_start_time():
    """The next recurrence carries over the original task's start_time."""
    task = make_task("t1", "Morning walk", 30, priority=3,
                     frequency="daily", start_time="07:30")
    scheduler = make_scheduler([task])
    next_task = scheduler.mark_task_complete("t1")
    assert next_task is not None
    assert next_task.start_time == "07:30"


# ---------------------------------------------------------------------------
# explain_plan – empty schedule message
# ---------------------------------------------------------------------------

def test_explain_plan_empty_schedule():
    """explain_plan reports that nothing could be scheduled when there are no tasks."""
    scheduler = make_scheduler([], budget=120)
    explanation = scheduler.explain_plan()
    assert "No tasks" in explanation


# ---------------------------------------------------------------------------
# RAG engine
# ---------------------------------------------------------------------------

def test_rag_retrieve_returns_relevant_chunks():
    """Querying for dog exercise returns at least one matching chunk."""
    from knowledge_base import PET_CARE_KNOWLEDGE
    from rag_engine import RAGEngine
    engine = RAGEngine(PET_CARE_KNOWLEDGE)
    results = engine.retrieve("how much exercise does a dog need")
    assert len(results) > 0
    assert any("dog" in chunk.lower() or "exercise" in chunk.lower()
               for chunk in results)


def test_rag_retrieve_empty_for_no_match():
    """A query with no vocabulary overlap returns an empty list."""
    from rag_engine import RAGEngine
    engine = RAGEngine(["Dog exercise: Dogs need daily walks."])
    results = engine.retrieve("xyzzy frobble quantum")
    assert results == []


def test_rag_build_user_message_contains_all_sections():
    """The assembled prompt includes knowledge, pet context, and the question."""
    from rag_engine import RAGEngine
    engine = RAGEngine(["Dog exercise: Dogs need walks."])
    msg = engine._build_user_message(
        question="How much exercise?",
        pet_context="Owner: Alex\nPet: Rex (dog)",
        retrieved=["Dog exercise: Dogs need walks."],
    )
    assert "RETRIEVED PET CARE KNOWLEDGE" in msg
    assert "OWNER'S CURRENT PET DATA" in msg
    assert "How much exercise?" in msg


def test_rag_build_user_message_no_chunks_fallback():
    """When no chunks are retrieved the message contains the fallback notice."""
    from rag_engine import RAGEngine
    engine = RAGEngine(["Dog exercise: Dogs need walks."])
    msg = engine._build_user_message(
        question="Any question?",
        pet_context="Owner: Alex",
        retrieved=[],
    )
    assert "No closely matching entries" in msg