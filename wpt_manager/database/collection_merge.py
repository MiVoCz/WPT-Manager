import sqlite3
from collections.abc import Mapping
from uuid import UUID, uuid4

from wpt_manager.database.database import Database
from wpt_manager.models.collection import Collection
from wpt_manager.models.collection_merge import (
    ConflictDecision,
    MergeConflict,
    MergePlan,
    MergeResult,
    WaypointMergePlan,
)
from wpt_manager.models.waypoint import Waypoint
from wpt_manager.validation.waypoint_duplicates import (
    DEFAULT_DUPLICATE_THRESHOLD_M,
    find_nearest_duplicate,
)


def prepare_collection_merge(
    database: Database,
    source_collection_id: UUID,
    target_collection_id: UUID,
    duplicate_threshold_m: float = DEFAULT_DUPLICATE_THRESHOLD_M,
) -> MergePlan:
    """Build a read-only plan for merging source into target."""
    connection = database._connect()
    try:
        return _prepare_merge(
            connection,
            source_collection_id,
            target_collection_id,
            duplicate_threshold_m,
        )
    finally:
        connection.close()


def merge_collections(
    database: Database,
    source_collection_id: UUID,
    target_collection_id: UUID,
    conflict_decisions: Mapping[UUID, ConflictDecision],
    duplicate_threshold_m: float = DEFAULT_DUPLICATE_THRESHOLD_M,
) -> MergeResult:
    """Atomically merge source waypoints into the target collection."""
    connection = database._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        plan = _prepare_merge(
            connection,
            source_collection_id,
            target_collection_id,
            duplicate_threshold_m,
        )
        result = _execute_waypoint_merge(
            connection,
            plan,
            target_collection_id,
            conflict_decisions,
        )
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _prepare_merge(
    connection: sqlite3.Connection,
    source_collection_id: UUID,
    target_collection_id: UUID,
    duplicate_threshold_m: float,
) -> MergePlan:
    if source_collection_id == target_collection_id:
        raise ValueError("Source and target collections must be different.")

    source_collection = _get_collection(connection, source_collection_id)
    if source_collection is None:
        raise ValueError(
            f"Source collection does not exist: {source_collection_id}"
        )
    target_collection = _get_collection(connection, target_collection_id)
    if target_collection is None:
        raise ValueError(
            f"Target collection does not exist: {target_collection_id}"
        )

    source_waypoints = _list_waypoints(connection, source_collection_id)
    target_waypoints = _list_waypoints(connection, target_collection_id)
    waypoint_plan = prepare_waypoint_merge(
        source_waypoints,
        target_waypoints,
        duplicate_threshold_m,
    )

    return MergePlan(
        source_collection=source_collection,
        target_collection=target_collection,
        new_waypoints=waypoint_plan.new_waypoints,
        conflicts=waypoint_plan.conflicts,
        duplicate_threshold_m=waypoint_plan.duplicate_threshold_m,
    )


def prepare_waypoint_merge(
    source_waypoints: list[Waypoint],
    target_waypoints: list[Waypoint],
    duplicate_threshold_m: float = DEFAULT_DUPLICATE_THRESHOLD_M,
) -> WaypointMergePlan:
    """Build a merge plan for an in-memory source dataset."""
    remaining_sources = list(source_waypoints)
    remaining_targets = list(target_waypoints)
    conflicts: list[MergeConflict] = []

    while remaining_sources and remaining_targets:
        candidate_matches = [
            match
            for source in remaining_sources
            if (
                match := find_nearest_duplicate(
                    source,
                    remaining_targets,
                    duplicate_threshold_m,
                )
            )
            is not None
        ]
        if not candidate_matches:
            break

        match = min(
            candidate_matches,
            key=lambda candidate: (
                candidate.distance_m,
                candidate.source.id.int,
                candidate.target.id.int,
            ),
        )
        conflicts.append(
            MergeConflict(
                source=match.source,
                target=match.target,
                distance_m=match.distance_m,
            )
        )
        remaining_sources = [
            source
            for source in remaining_sources
            if source.id != match.source.id
        ]
        remaining_targets = [
            target
            for target in remaining_targets
            if target.id != match.target.id
        ]

    return WaypointMergePlan(
        new_waypoints=tuple(remaining_sources),
        conflicts=tuple(conflicts),
        duplicate_threshold_m=duplicate_threshold_m,
    )


def merge_waypoints_into_collection(
    database: Database,
    source_waypoints: list[Waypoint],
    target_collection_id: UUID,
    conflict_decisions: Mapping[UUID, ConflictDecision],
    duplicate_threshold_m: float = DEFAULT_DUPLICATE_THRESHOLD_M,
) -> MergeResult:
    """Atomically merge an in-memory source dataset into a Collection."""
    connection = database._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        if _get_collection(connection, target_collection_id) is None:
            raise ValueError(
                f"Target collection does not exist: {target_collection_id}"
            )
        plan = prepare_waypoint_merge(
            source_waypoints,
            _list_waypoints(connection, target_collection_id),
            duplicate_threshold_m,
        )
        result = _execute_waypoint_merge(
            connection,
            plan,
            target_collection_id,
            conflict_decisions,
        )
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _execute_waypoint_merge(
    connection: sqlite3.Connection,
    plan: MergePlan | WaypointMergePlan,
    target_collection_id: UUID,
    conflict_decisions: Mapping[UUID, ConflictDecision],
) -> MergeResult:
    _validate_decisions(plan, conflict_decisions)
    added_count = 0
    replaced_count = 0
    skipped_count = 0
    kept_both_count = 0

    for waypoint in plan.new_waypoints:
        _insert_waypoint_copy(connection, waypoint, target_collection_id)
        added_count += 1

    for conflict in plan.conflicts:
        decision = conflict_decisions[conflict.source.id]
        if decision is ConflictDecision.KEEP_TARGET:
            skipped_count += 1
        elif decision is ConflictDecision.USE_SOURCE:
            _replace_target_waypoint(
                connection,
                conflict.target.id,
                conflict.source,
            )
            replaced_count += 1
        else:
            _insert_waypoint_copy(
                connection,
                conflict.source,
                target_collection_id,
            )
            added_count += 1
            kept_both_count += 1

    return MergeResult(
        added_count=added_count,
        replaced_count=replaced_count,
        skipped_count=skipped_count,
        kept_both_count=kept_both_count,
    )


def _validate_decisions(
    plan: MergePlan | WaypointMergePlan,
    decisions: Mapping[UUID, ConflictDecision],
) -> None:
    conflict_ids = {conflict.source.id for conflict in plan.conflicts}
    decision_ids = set(decisions)
    if decision_ids != conflict_ids:
        raise ValueError("Decisions must be provided for every conflict.")
    if any(
        not isinstance(decision, ConflictDecision)
        for decision in decisions.values()
    ):
        raise ValueError("Every conflict decision must be explicit.")


def _get_collection(
    connection: sqlite3.Connection,
    collection_id: UUID,
) -> Collection | None:
    row = connection.execute(
        """
        SELECT id, name, description, source, source_file
        FROM collections
        WHERE id = ?
        """,
        (str(collection_id),),
    ).fetchone()
    if row is None:
        return None
    return Collection(
        id=UUID(row[0]),
        name=row[1],
        description=row[2],
        source=row[3],
        source_file=row[4],
    )


def _list_waypoints(
    connection: sqlite3.Connection,
    collection_id: UUID,
) -> list[Waypoint]:
    rows = connection.execute(
        """
        SELECT id, name, latitude, longitude, icon, color,
               background, note, comment
        FROM waypoints
        WHERE collection_id = ?
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """,
        (str(collection_id),),
    ).fetchall()
    return [
        Waypoint(
            id=UUID(row[0]),
            name=row[1],
            latitude=row[2],
            longitude=row[3],
            icon=row[4],
            color=row[5],
            background=row[6],
            note=row[7],
            comment=row[8],
        )
        for row in rows
    ]


def _insert_waypoint_copy(
    connection: sqlite3.Connection,
    waypoint: Waypoint,
    target_collection_id: UUID,
) -> None:
    connection.execute(
        """
        INSERT INTO waypoints (
            id, collection_id, name, latitude, longitude,
            icon, color, background, note, comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            str(target_collection_id),
            waypoint.name,
            waypoint.latitude,
            waypoint.longitude,
            waypoint.icon,
            waypoint.color,
            waypoint.background,
            waypoint.note,
            waypoint.comment,
        ),
    )


def _replace_target_waypoint(
    connection: sqlite3.Connection,
    target_waypoint_id: UUID,
    source: Waypoint,
) -> None:
    connection.execute(
        """
        UPDATE waypoints
        SET name = ?, latitude = ?, longitude = ?, icon = ?, color = ?,
            background = ?, note = ?, comment = ?
        WHERE id = ?
        """,
        (
            source.name,
            source.latitude,
            source.longitude,
            source.icon,
            source.color,
            source.background,
            source.note,
            source.comment,
            str(target_waypoint_id),
        ),
    )
