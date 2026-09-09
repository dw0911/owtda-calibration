"""OW-TDA-CAL-R1 identity core (B03, L0 code).

This package implements the canonical-serialization and cryptographic identity
contracts of Plan §15.2-§15.4:
  - canonical JSON / canonical decimal text / single-object content hash;
  - ``H(id_kind, **named_fields)`` and derived registry hashes;
  - HMAC sub-seed derivation feeding ``PCG64DXSM`` RNGs;
  - big-endian array / float hash-view / file bytes contracts.

Nothing in this package consumes formal RNG streams or produces science rows.
"""

__version__ = "0.1.0"

PROJECT_ID = "owtda-cal-r1"
ID_DOMAIN = "owtda-id-v1"
SEED_DOMAIN = "owtda-seed-v1"
ARRAY_DOMAIN = "owtda-array-v1"

from .canonical import (
    CanonicalizationError,
    canonical_decimal_text,
    canonical_json,
    canonical_json_bytes,
    single_object_content_hash,
)
from .hashing import (
    array_bytes,
    array_hash,
    f64_view,
    file_sha256,
)
from .identity import (
    H,
    config_hash,
    expected_id_set_hash,
    file_manifest_hash,
    file_manifest_hash_from_tree,
    root_entry_hash,
)
from .seeding import (
    derive_seed_hex,
    derive_seed_int,
    make_rng,
    root_key_commitment,
)

__all__ = [
    "__version__",
    "PROJECT_ID",
    "ID_DOMAIN",
    "SEED_DOMAIN",
    "ARRAY_DOMAIN",
    # canonical
    "CanonicalizationError",
    "canonical_decimal_text",
    "canonical_json",
    "canonical_json_bytes",
    "single_object_content_hash",
    # identity
    "H",
    "config_hash",
    "file_manifest_hash",
    "file_manifest_hash_from_tree",
    "expected_id_set_hash",
    "root_entry_hash",
    # seeding
    "derive_seed_hex",
    "derive_seed_int",
    "make_rng",
    "root_key_commitment",
    # hashing
    "file_sha256",
    "array_bytes",
    "array_hash",
    "f64_view",
]
