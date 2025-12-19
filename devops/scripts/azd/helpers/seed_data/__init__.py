from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable, Mapping, Sequence, Tuple

_DATASET_MODULES = {
    "insurance": "seed_data.insurance",
    "financial": "seed_data.financial",
}


@dataclass(frozen=True)
class SeedTask:
    """Immutable description of a dataset seeding task.

    Attributes:
        dataset: Logical dataset identifier.
        database: Cosmos DB database name.
        collection: Cosmos DB collection name.
        documents: Documents to upsert.
        id_field: Primary identifier field used for upsert queries.

    Latency:
        Pure data container; no runtime cost.
    """

    dataset: str
    database: str
    collection: str
    documents: Sequence[dict]
    id_field: str


def list_datasets() -> Tuple[str, ...]:
    """Return the registered dataset identifiers.

    Returns:
        Tuple of dataset keys available for seeding.

    Latency:
        O(1) dictionary lookup.
    """
    return tuple(_DATASET_MODULES.keys())


def _resolve_dataset(name: str) -> Callable[[Mapping[str, object]], Sequence[SeedTask]]:
    """Import the dataset module and return its task factory.

    Args:
        name: Dataset identifier.

    Returns:
        Callable that produces seed tasks for the dataset.

    Latency:
        Dominated by a single module import per dataset.
    """
    module = import_module(_DATASET_MODULES[name])
    getter: Callable[[Mapping[str, object]], Sequence[SeedTask]] = getattr(module, "get_seed_tasks")
    return getter


def load_seed_tasks(names: Sequence[str], options: Mapping[str, object]) -> Sequence[SeedTask]:
    """Load seed tasks for the requested datasets.

    Args:
        names: Dataset identifiers to load.
        options: Shared options forwarded to each dataset module.

    Returns:
        Tuple of SeedTask instances ready for execution.

    Latency:
        Linear in the number of datasets imported.
    """
    tasks: list[SeedTask] = []
    for name in names:
        if name not in _DATASET_MODULES:
            raise KeyError(f"Unknown dataset '{name}'")
        getter = _resolve_dataset(name)
        tasks.extend(getter(options))
    return tuple(tasks)
