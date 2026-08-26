from uuid import uuid4

import pytest

import wpt_manager.database.collection_merge as collection_merge_module
from wpt_manager.database.collection_merge import (
    MergePlanChangedError,
    merge_collections,
    merge_waypoints_into_collection,
    prepare_collection_merge,
    prepare_waypoint_merge,
)
from wpt_manager.database.database import Database
from wpt_manager.models.collection import Collection
from wpt_manager.models.collection_merge import ConflictDecision
from wpt_manager.models.waypoint import Waypoint


def create_database_with_collections(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    source = Collection(name="Source")
    target = Collection(name="Target")
    database.save_collection(source)
    database.save_collection(target)
    return database, source, target


def waypoint(name: str, latitude: float, **values) -> Waypoint:
    return Waypoint(
        name=name,
        latitude=latitude,
        longitude=14.0,
        **values,
    )


def test_single_target_is_matched_only_to_nearest_source():
    nearest_source = waypoint("Nearest source", 50.00001)
    farther_source = waypoint("Farther source", 50.00010)
    target = waypoint("Target", 50.0)

    plan = prepare_waypoint_merge(
        [farther_source, nearest_source],
        [target],
    )

    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].source is nearest_source
    assert plan.conflicts[0].target is target
    assert plan.new_waypoints == (farther_source,)


def test_sources_match_nearest_available_distinct_targets():
    first_source = waypoint("First source", 50.0)
    second_source = waypoint("Second source", 50.00030)
    first_target = waypoint("First target", 50.00005)
    second_target = waypoint("Second target", 50.00035)

    plan = prepare_waypoint_merge(
        [first_source, second_source],
        [first_target, second_target],
    )

    matches = {
        conflict.source.id: conflict.target.id
        for conflict in plan.conflicts
    }
    assert matches == {
        first_source.id: first_target.id,
        second_source.id: second_target.id,
    }
    assert plan.new_waypoints == ()


def test_source_order_does_not_change_one_to_one_matching():
    first_source = waypoint("First source", 50.0)
    second_source = waypoint("Second source", 50.00030)
    first_target = waypoint("First target", 50.00005)
    second_target = waypoint("Second target", 50.00035)

    forward = prepare_waypoint_merge(
        [first_source, second_source],
        [first_target, second_target],
    )
    reversed_sources = prepare_waypoint_merge(
        [second_source, first_source],
        [first_target, second_target],
    )

    def matches(plan):
        return {
            conflict.source.id: conflict.target.id
            for conflict in plan.conflicts
        }

    assert matches(forward) == matches(reversed_sources)


def test_use_source_replaces_each_target_at_most_once(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    nearest_source = waypoint("Nearest source", 50.00001)
    farther_source = waypoint("Farther source", 50.00010)
    target_waypoint = waypoint("Target", 50.0)
    database.save_waypoint(farther_source, source.id)
    database.save_waypoint(nearest_source, source.id)
    database.save_waypoint(target_waypoint, target.id)

    plan = prepare_collection_merge(database, source.id, target.id)
    result = merge_collections(
        database,
        source.id,
        target.id,
        {
            plan.conflicts[0].source.id: ConflictDecision.USE_SOURCE,
        },
    )

    assert result.replaced_count == 1
    assert result.added_count == 1
    replaced = database.get_waypoint(target_waypoint.id)
    assert replaced is not None
    assert replaced.name == nearest_source.name
    assert len(database.list_waypoints(target.id)) == 2


def test_merge_without_conflicts(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    source_waypoint = waypoint("Source point", 50.0)
    target_waypoint = waypoint("Target point", 51.0)
    database.save_waypoint(source_waypoint, source.id)
    database.save_waypoint(target_waypoint, target.id)

    plan = prepare_collection_merge(database, source.id, target.id)

    assert plan.source_collection == source
    assert plan.target_collection == target
    assert plan.new_waypoints == (source_waypoint,)
    assert plan.conflicts == ()
    assert plan.duplicate_threshold_m == 50.0
    assert database.list_waypoints(target.id) == [target_waypoint]

    result = merge_collections(database, source.id, target.id, {})

    assert result.added_count == 1
    assert result.replaced_count == 0
    assert result.skipped_count == 0
    assert result.kept_both_count == 0
    merged = database.list_waypoints(target.id)
    copied = next(item for item in merged if item.name == source_waypoint.name)
    assert copied.id != source_waypoint.id


def test_keep_target_skips_source_waypoint(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    source_waypoint = waypoint("Source point", 50.0)
    target_waypoint = waypoint("Target point", 50.0)
    database.save_waypoint(source_waypoint, source.id)
    database.save_waypoint(target_waypoint, target.id)

    result = merge_collections(
        database,
        source.id,
        target.id,
        {source_waypoint.id: ConflictDecision.KEEP_TARGET},
    )

    assert result.skipped_count == 1
    assert result.added_count == 0
    assert database.list_waypoints(target.id) == [target_waypoint]


def test_use_source_replaces_target_content(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    source_waypoint = waypoint(
        "Source point",
        50.0,
        icon="source-icon",
        color="#123456",
        background="square",
        note="source note",
        comment="source comment",
    )
    target_waypoint = waypoint("Target point", 50.0)
    database.save_waypoint(source_waypoint, source.id)
    database.save_waypoint(target_waypoint, target.id)

    result = merge_collections(
        database,
        source.id,
        target.id,
        {source_waypoint.id: ConflictDecision.USE_SOURCE},
    )

    replaced = database.list_waypoints(target.id)[0]
    assert result.replaced_count == 1
    assert replaced.id == target_waypoint.id
    assert replaced.name == source_waypoint.name
    assert replaced.latitude == source_waypoint.latitude
    assert replaced.longitude == source_waypoint.longitude
    assert replaced.icon == source_waypoint.icon
    assert replaced.color == source_waypoint.color
    assert replaced.background == source_waypoint.background
    assert replaced.note == source_waypoint.note
    assert replaced.comment == source_waypoint.comment


def test_keep_both_adds_source_copy(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    source_waypoint = waypoint("Source point", 50.0)
    target_waypoint = waypoint("Target point", 50.0)
    database.save_waypoint(source_waypoint, source.id)
    database.save_waypoint(target_waypoint, target.id)

    result = merge_collections(
        database,
        source.id,
        target.id,
        {source_waypoint.id: ConflictDecision.KEEP_BOTH},
    )

    merged = database.list_waypoints(target.id)
    assert result.added_count == 1
    assert result.kept_both_count == 1
    assert target_waypoint in merged
    copied = next(item for item in merged if item.name == source_waypoint.name)
    assert copied.id not in {source_waypoint.id, target_waypoint.id}
    assert database.get_waypoint(source_waypoint.id) == source_waypoint


def test_source_collection_remains_unchanged_after_merge(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    conflicting = waypoint("Conflicting", 50.0)
    new = waypoint("New", 51.0)
    target_waypoint = waypoint("Target", 50.0)
    database.save_waypoint(conflicting, source.id)
    database.save_waypoint(new, source.id)
    database.save_waypoint(target_waypoint, target.id)
    original_source_waypoints = database.list_waypoints(source.id)

    merge_collections(
        database,
        source.id,
        target.id,
        {conflicting.id: ConflictDecision.USE_SOURCE},
    )

    assert database.get_collection(source.id) == source
    assert database.list_waypoints(source.id) == original_source_waypoints


def test_same_source_and_target_collection_fails(tmp_path):
    database, source, _ = create_database_with_collections(tmp_path)

    with pytest.raises(ValueError, match="must be different"):
        prepare_collection_merge(database, source.id, source.id)
    with pytest.raises(ValueError, match="must be different"):
        merge_collections(database, source.id, source.id, {})


def test_missing_source_collection_fails(tmp_path):
    database, _, target = create_database_with_collections(tmp_path)

    with pytest.raises(ValueError, match="Source collection does not exist"):
        merge_collections(database, uuid4(), target.id, {})


def test_missing_target_collection_fails(tmp_path):
    database, source, _ = create_database_with_collections(tmp_path)

    with pytest.raises(ValueError, match="Target collection does not exist"):
        merge_collections(database, source.id, uuid4(), {})


def test_error_during_merge_rolls_back_all_changes(tmp_path, monkeypatch):
    database, source, target = create_database_with_collections(tmp_path)
    database.save_waypoint(waypoint("First", 50.0), source.id)
    database.save_waypoint(waypoint("Second", 51.0), source.id)
    original_insert = collection_merge_module._insert_waypoint_copy
    calls = 0

    def fail_on_second_insert(connection, source_waypoint, target_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Simulated merge failure")
        original_insert(connection, source_waypoint, target_id)

    monkeypatch.setattr(
        collection_merge_module,
        "_insert_waypoint_copy",
        fail_on_second_insert,
    )

    with pytest.raises(RuntimeError, match="Simulated merge failure"):
        merge_collections(database, source.id, target.id, {})

    assert database.list_waypoints(target.id) == []


def test_in_memory_waypoint_merge_rolls_back_all_changes(
    tmp_path,
    monkeypatch,
):
    database, _, target = create_database_with_collections(tmp_path)
    source_waypoints = [
        waypoint("First", 50.0),
        waypoint("Second", 51.0),
    ]
    original_insert = collection_merge_module._insert_waypoint_copy
    calls = 0

    def fail_on_second_insert(connection, source_waypoint, target_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Simulated import failure")
        original_insert(connection, source_waypoint, target_id)

    monkeypatch.setattr(
        collection_merge_module,
        "_insert_waypoint_copy",
        fail_on_second_insert,
    )

    with pytest.raises(RuntimeError, match="Simulated import failure"):
        merge_waypoints_into_collection(
            database,
            source_waypoints,
            target.id,
            {},
        )

    assert database.list_waypoints(target.id) == []


def test_multiple_conflicts_accept_different_decisions(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    skipped = waypoint("Skipped source", 50.0)
    replaced = waypoint("Replacement source", 51.0)
    kept = waypoint("Kept source", 52.0)
    for item in (skipped, replaced, kept):
        database.save_waypoint(item, source.id)
    skipped_target = waypoint("Skipped target", 50.0)
    replaced_target = waypoint("Replaced target", 51.0)
    kept_target = waypoint("Kept target", 52.0)
    for item in (skipped_target, replaced_target, kept_target):
        database.save_waypoint(item, target.id)

    result = merge_collections(
        database,
        source.id,
        target.id,
        {
            skipped.id: ConflictDecision.KEEP_TARGET,
            replaced.id: ConflictDecision.USE_SOURCE,
            kept.id: ConflictDecision.KEEP_BOTH,
        },
    )

    assert result.added_count == 1
    assert result.replaced_count == 1
    assert result.skipped_count == 1
    assert result.kept_both_count == 1
    merged = database.list_waypoints(target.id)
    assert len(merged) == 4
    assert database.get_waypoint(skipped_target.id) == skipped_target
    assert database.get_waypoint(replaced_target.id).name == replaced.name
    assert database.get_waypoint(kept_target.id) == kept_target


def test_all_conflicts_require_explicit_decisions(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    source_waypoint = waypoint("Source", 50.0)
    database.save_waypoint(source_waypoint, source.id)
    database.save_waypoint(waypoint("Target", 50.0), target.id)

    with pytest.raises(ValueError, match="every conflict"):
        merge_collections(database, source.id, target.id, {})

    assert len(database.list_waypoints(target.id)) == 1


def test_custom_duplicate_threshold_is_used_in_plan(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    source_waypoint = waypoint("Source", 50.0)
    nearby = waypoint("Target", 50.0006)
    database.save_waypoint(source_waypoint, source.id)
    database.save_waypoint(nearby, target.id)

    default_plan = prepare_collection_merge(database, source.id, target.id)
    wider_plan = prepare_collection_merge(
        database,
        source.id,
        target.id,
        duplicate_threshold_m=70.0,
    )

    assert default_plan.new_waypoints == (source_waypoint,)
    assert wider_plan.conflicts[0].source == source_waypoint


@pytest.mark.parametrize("target_change", ["add", "update", "delete"])
def test_collection_merge_rejects_target_changed_since_analysis(
    tmp_path,
    target_change,
):
    database, source, target = create_database_with_collections(tmp_path)
    database.save_waypoint(waypoint("Source", 50.0), source.id)
    original_target = waypoint("Target", 51.0)
    database.save_waypoint(original_target, target.id)
    plan = prepare_collection_merge(database, source.id, target.id)

    if target_change == "add":
        database.save_waypoint(waypoint("Added", 52.0), target.id)
    elif target_change == "update":
        original_target.name = "Updated target"
        database.update_waypoint(original_target)
    else:
        database.delete_waypoint(original_target.id)
    source_before = database.list_waypoints(source.id)
    target_before = database.list_waypoints(target.id)

    with pytest.raises(MergePlanChangedError, match="analyze again"):
        merge_collections(
            database,
            source.id,
            target.id,
            {},
            analyzed_plan=plan,
        )

    assert database.list_waypoints(source.id) == source_before
    assert database.list_waypoints(target.id) == target_before


def test_collection_merge_rejects_source_changed_since_analysis(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    database.save_waypoint(waypoint("Source", 50.0), source.id)
    plan = prepare_collection_merge(database, source.id, target.id)
    database.save_waypoint(waypoint("New source", 51.0), source.id)
    source_before = database.list_waypoints(source.id)

    with pytest.raises(MergePlanChangedError, match="analyze again"):
        merge_collections(
            database,
            source.id,
            target.id,
            {},
            analyzed_plan=plan,
        )

    assert database.list_waypoints(source.id) == source_before
    assert database.list_waypoints(target.id) == []


def test_collection_merge_succeeds_after_new_analysis(tmp_path):
    database, source, target = create_database_with_collections(tmp_path)
    database.save_waypoint(waypoint("Source", 50.0), source.id)
    stale_plan = prepare_collection_merge(database, source.id, target.id)
    database.save_waypoint(waypoint("Changed target", 51.0), target.id)

    with pytest.raises(MergePlanChangedError):
        merge_collections(
            database,
            source.id,
            target.id,
            {},
            analyzed_plan=stale_plan,
        )

    current_plan = prepare_collection_merge(database, source.id, target.id)
    result = merge_collections(
        database,
        source.id,
        target.id,
        {},
        analyzed_plan=current_plan,
    )

    assert result.added_count == 1


def test_in_memory_merge_rejects_target_changed_since_analysis(tmp_path):
    database, _, target = create_database_with_collections(tmp_path)
    source_waypoints = [waypoint("Imported", 50.0)]
    plan = prepare_waypoint_merge(source_waypoints, [])
    added_target = waypoint("Added target", 51.0)
    database.save_waypoint(added_target, target.id)

    with pytest.raises(MergePlanChangedError, match="analyze again"):
        merge_waypoints_into_collection(
            database,
            source_waypoints,
            target.id,
            {},
            analyzed_plan=plan,
        )

    assert database.list_waypoints(target.id) == [added_target]
