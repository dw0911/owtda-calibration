"""Golden tests for ID hashes (Plan §15.1, §15.3, §15.4)."""

import hashlib

import pytest

from owtda_cal import (
    H,
    config_hash,
    expected_id_set_hash,
    file_manifest_hash,
    file_manifest_hash_from_tree,
    root_entry_hash,
)

_AA = "a" * 64


class TestH:
    def test_golden_bytes(self):
        # sorted key order: a, b, domain, id_kind
        expected = hashlib.sha256(
            b'{"a":1,"b":"x","domain":"owtda-id-v1","id_kind":"demo"}'
        ).hexdigest()
        assert H("demo", a=1, b="x") == expected

    def test_kwargs_order_insensitive(self):
        a = H("demo", x=1, y=2)
        b = H("demo", y=2, x=1)
        assert a == b
        assert len(a) == 64

    def test_reserved_keys_rejected(self):
        with pytest.raises(ValueError):
            H("demo", domain="x")
        # "id_kind" is already bound as H's first positional parameter, so a
        # second binding is a TypeError at the call site (equally a rejection).
        with pytest.raises(TypeError):
            H("demo", id_kind="x")

    def test_invalid_id_kind_rejected(self):
        with pytest.raises(ValueError):
            H("")
        with pytest.raises(ValueError):
            H("bad kind!")
        with pytest.raises(ValueError):
            H("9kind")

    def test_nested_object_canonicalised(self):
        expected = hashlib.sha256(
            b'{"a":{"b":1,"c":2},"domain":"owtda-id-v1","id_kind":"nested"}'
        ).hexdigest()
        assert H("nested", a={"c": 2, "b": 1}) == expected


class TestConfigHash:
    def test_golden(self):
        expected = hashlib.sha256(
            b'{"config":{"a":2,"b":1},"config_kind":"testcfg","domain":"owtda-id-v1",'
            b'"id_kind":"config","schema_version":"1"}'
        ).hexdigest()
        assert config_hash("testcfg", "1", {"b": 1, "a": 2}) == expected


class TestFileManifestHash:
    def test_sorted_and_golden(self):
        entries = [
            {"path": "b.txt", "size": 3, "file_sha256": _AA},
            {"path": "a.txt", "size": 1, "file_sha256": _AA},
        ]
        expected = hashlib.sha256(
            b'{"domain":"owtda-id-v1","id_kind":"file_manifest","manifest_entries":['
            b'{"file_sha256":"' + _AA.encode() +
            b'","path":"a.txt","size":1},'
            b'{"file_sha256":"' + _AA.encode() +
            b'","path":"b.txt","size":3}]}'
        ).hexdigest()
        assert file_manifest_hash(entries) == expected

    def test_tamper_any_field_changes_hash(self):
        base = [{"path": "a.txt", "size": 1, "file_sha256": _AA}]
        h0 = file_manifest_hash(base)
        assert file_manifest_hash([{"path": "b.txt", "size": 1, "file_sha256": _AA}]) != h0
        assert file_manifest_hash([{"path": "a.txt", "size": 2, "file_sha256": _AA}]) != h0
        assert file_manifest_hash(
            [{"path": "a.txt", "size": 1, "file_sha256": "b" * 64}]
        ) != h0

    def test_duplicate_path_rejected(self):
        with pytest.raises(ValueError):
            file_manifest_hash(
                [
                    {"path": "a.txt", "size": 1, "file_sha256": _AA},
                    {"path": "a.txt", "size": 2, "file_sha256": _AA},
                ]
            )

    def test_bad_path_rejected(self):
        for path in ("", "a\\b.txt", "/a.txt", "a/./b.txt", "a/../b.txt", "a//b.txt"):
            with pytest.raises(ValueError):
                file_manifest_hash([{"path": path, "size": 1, "file_sha256": _AA}])

    def test_subdirectory_path_accepted(self):
        assert len(file_manifest_hash([{"path": "x/y.txt", "size": 1, "file_sha256": _AA}])) == 64

    def test_missing_key_or_bad_sha_rejected(self):
        with pytest.raises(ValueError):
            file_manifest_hash([{"path": "a.txt", "file_sha256": _AA}])
        with pytest.raises(ValueError):
            file_manifest_hash([{"path": "a.txt", "size": 1, "file_sha256": "zz"}])

    def test_from_tree_triples(self):
        a = file_manifest_hash([{"path": "x/y.txt", "size": 2, "file_sha256": _AA}])
        b = file_manifest_hash_from_tree([("x/y.txt", 2, _AA)])
        assert a == b


class TestExpectedIdSetHash:
    def test_dedup_sorted_golden(self):
        expected = hashlib.sha256(
            b'{"domain":"owtda-id-v1","id_kind":"expected_id_set","ids":['
            b'"' + ("1" * 64).encode() + b'","' + ("2" * 64).encode() + b'"]}'
        ).hexdigest()
        ids = ["2" * 64, "1" * 64, "2" * 64]
        assert expected_id_set_hash(ids) == expected

    def test_bad_id_rejected(self):
        with pytest.raises(ValueError):
            expected_id_set_hash(["xyz"])


class TestRootEntryHash:
    def test_signature_and_64hex(self):
        h = root_entry_hash(
            project_id="owtda-cal-r1",
            protocol_id="p",
            freeze_id="f",
            evidence_generation_id="G01",
            phase="NULL",
            stream_family="null_data",
            component_generation_id="D01",
            root_key_commitment=_AA,
        )
        assert len(h) == 64
        with pytest.raises(ValueError):
            root_entry_hash(
                project_id="owtda-cal-r1",
                protocol_id="p",
                freeze_id="f",
                evidence_generation_id="G01",
                phase="NULL",
                stream_family="null_data",
                component_generation_id="D01",
                root_key_commitment="not-a-hash",
            )
