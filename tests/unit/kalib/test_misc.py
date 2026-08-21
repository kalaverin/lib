"""Tests for `zx.lib.misc` — iterators, process title, sampling hash."""

import sys
from pathlib import Path

import pytest
from faker import Faker

from zx.lib import misc

pytestmark = pytest.mark.serial

SEQUENCE_SIZES = (1, 2, 3, 5, 8, 100)
SEQUENCE_IDS = tuple(f"size-{size}" for size in SEQUENCE_SIZES)

FALLBACK_SIZES = (1, 2)
FALLBACK_IDS = ("single", "pair")

PERMUTATION_SIZES = (3, 5, 17)
PERMUTATION_IDS = tuple(f"unique-{size}" for size in PERMUTATION_SIZES)
BATCH_SIZE = 5

FILE_SIZES = (2, 3, 100, 4095, 4096, 4097, 8192, 8193, 16384)
FILE_SIZE_IDS = tuple(f"bytes-{size}" for size in FILE_SIZES)
DEFAULT_SAMPLE_SIZE = 4097
XXH128_HEX_LENGTH = 32
SHA1_HEX_LENGTH = 40


# --- cycler ---


@pytest.mark.parametrize("size", SEQUENCE_SIZES, ids=SEQUENCE_IDS)
def test_cycler_parametrized_size_repeats_sequence_verbatim(size: int) -> None:
    """
    Given: a sequence of parametrized length.
    When: more than two full cycles are drawn from the cycler.
    Then: the values repeat the sequence verbatim, cycle after cycle.
    """
    # --- Arrange ---
    items = tuple(f"item-{index}" for index in range(size))
    draw = misc.cycler(items)
    draws = size * 2 + 1

    # --- Act ---
    produced = tuple(draw() for _ in range(draws))

    # --- Assert ---
    repeated = (items * (draws // size + 1))[:draws]
    assert produced == repeated


# --- shuffler ---


@pytest.mark.parametrize("size", FALLBACK_SIZES, ids=FALLBACK_IDS)
def test_shuffler_below_threshold_falls_back_to_cycler(size: int) -> None:
    """
    Given: an iterable shorter than the shuffle threshold of 3 items.
    When: values are drawn beyond one full pass.
    Then: the shuffler degenerates to verbatim cycler repetition.
    """
    # --- Arrange ---
    items = tuple(f"item-{index}" for index in range(size))
    draw = misc.shuffler(items)
    draws = size * 2 + 1

    # --- Act ---
    produced = tuple(draw() for _ in range(draws))

    # --- Assert ---
    repeated = (items * (draws // size + 1))[:draws]
    assert produced == repeated


@pytest.mark.parametrize("size", PERMUTATION_SIZES, ids=PERMUTATION_IDS)
def test_shuffler_unique_items_yields_permutation(
    fake: Faker,
    size: int,
) -> None:
    """
    Given: an iterable of parametrized length with unique items.
    When: one full batch is drawn from the shuffler.
    Then: the batch is a permutation of the input — the same multiset.
    """
    # --- Arrange ---
    items = tuple(f"{fake.word()}-{index}" for index in range(size))
    draw = misc.shuffler(items)

    # --- Act ---
    batch = tuple(draw() for _ in range(size))

    # --- Assert ---
    assert sorted(batch) == sorted(items)
    assert set(batch) == set(items)


def test_shuffler_consecutive_batches_do_not_repeat_boundary(
    fake: Faker,
) -> None:
    """
    Given: an iterable of unique items large enough to be shuffled.
    When: two full batches are drawn back to back.
    Then: the first item of the second batch is not the last of the first.
    """
    # --- Arrange ---
    items = tuple(f"{fake.word()}-{index}" for index in range(BATCH_SIZE))
    draw = misc.shuffler(items)

    # --- Act ---
    first = tuple(draw() for _ in range(BATCH_SIZE))
    second = tuple(draw() for _ in range(BATCH_SIZE))

    # --- Assert ---
    assert second[0] != first[-1]


# --- set_title ---


@pytest.fixture
def title_recorder(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture the process title; the real setproctitle is never called."""
    captured: list[str] = []
    monkeypatch.setattr(misc, "setproctitle", captured.append)
    return captured


def test_set_title_explicit_title_uses_title_verbatim(
    title_recorder: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an explicit title and an argv carrying an unrelated script name.
    When: set_title is called.
    Then: the explicit title is set verbatim and argv is ignored.
    """
    # --- Arrange ---
    title = "zx.lib-unit-test"
    monkeypatch.setattr(sys, "argv", ["unrelated-script", "noise"])

    # --- Act ---
    misc.set_title(title)

    # --- Assert ---
    assert title_recorder == [title]


def test_set_title_argv0_without_suffix_derives_stem(
    title_recorder: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an argv[0] pointing at a suffix-less binary path.
    When: set_title is called with defaults.
    Then: the title is the path stem and arguments stay stripped.
    """
    # --- Arrange ---
    monkeypatch.setattr(
        sys,
        "argv",
        ["/usr/local/bin/zxlib-tool", "--verbose"],
    )

    # --- Act ---
    misc.set_title()

    # --- Assert ---
    assert title_recorder == ["zxlib-tool"]


def test_set_title_py_suffix_full_form_drops_argv0(
    title_recorder: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a .py argv[0] with extra arguments, short form disabled.
    When: set_title is called.
    Then: argv[0] is dropped and the remaining arguments follow the stem.
    """
    # --- Arrange ---
    monkeypatch.setattr(sys, "argv", ["/opt/app/tool.py", "--flag", "value"])

    # --- Act ---
    misc.set_title(short=False)

    # --- Assert ---
    assert title_recorder == ["tool --flag value"]


def test_set_title_non_py_full_form_keeps_argv0(
    title_recorder: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a non-.py argv[0] with extra arguments, short form disabled.
    When: set_title is called.
    Then: the full form keeps argv[0] — only .py scripts drop it.
    """
    # --- Arrange ---
    monkeypatch.setattr(sys, "argv", ["/opt/app/tool", "--flag"])

    # --- Act ---
    misc.set_title(short=False)

    # --- Assert ---
    assert title_recorder == ["tool /opt/app/tool --flag"]


def test_set_title_short_true_strips_arguments(
    title_recorder: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a .py argv[0] with trailing arguments, short form enabled.
    When: set_title is called.
    Then: only the stem is set; no argument leaks into the title.
    """
    # --- Arrange ---
    monkeypatch.setattr(sys, "argv", ["/opt/app/tool.py", "--flag", "value"])

    # --- Act ---
    misc.set_title(short=True)

    # --- Assert ---
    assert title_recorder == ["tool"]


# --- fasthash ---


@pytest.mark.parametrize("size", FILE_SIZES, ids=FILE_SIZE_IDS)
def test_fasthash_same_content_returns_same_hash(
    fake: Faker,
    tmp_path: Path,
    size: int,
) -> None:
    """
    Given: a file of parametrized size with fixed faker-driven bytes.
    When: fasthash digests it twice.
    Then: both digests are identical 128-bit xxh128 hexdigests.
    """
    # --- Arrange ---
    document = tmp_path / f"blob-{size}.bin"
    document.write_bytes(fake.binary(length=size))

    # --- Act ---
    first = misc.fasthash(document)
    second = misc.fasthash(document)

    # --- Assert ---
    assert first == second
    assert len(first) == XXH128_HEX_LENGTH


@pytest.mark.parametrize("size", FILE_SIZES, ids=FILE_SIZE_IDS)
def test_fasthash_different_content_returns_different_hash(
    fake: Faker,
    tmp_path: Path,
    size: int,
) -> None:
    """
    Given: two files of equal size whose first byte differs.
    When: both are digested.
    Then: the digests differ.
    """
    # --- Arrange ---
    content = fake.binary(length=size)
    mutated = bytearray(content)
    mutated[0] ^= 0xFF
    left = tmp_path / "left.bin"
    right = tmp_path / "right.bin"
    left.write_bytes(content)
    right.write_bytes(bytes(mutated))

    # --- Act ---
    left_digest = misc.fasthash(left)
    right_digest = misc.fasthash(right)

    # --- Assert ---
    assert left_digest != right_digest


@pytest.mark.parametrize("size", FILE_SIZES, ids=FILE_SIZE_IDS)
def test_fasthash_size_participates_in_digest(
    fake: Faker,
    tmp_path: Path,
    size: int,
) -> None:
    """
    Given: a file and its strict extension by one byte.
    When: both are digested.
    Then: the digests differ although one content is a prefix of the other.
    """
    # --- Arrange ---
    content = fake.binary(length=size)
    whole = tmp_path / "whole.bin"
    extended = tmp_path / "extended.bin"
    whole.write_bytes(content)
    extended.write_bytes(content + b"\x01")

    # --- Act ---
    whole_digest = misc.fasthash(whole)
    extended_digest = misc.fasthash(extended)

    # --- Assert ---
    assert whole_digest != extended_digest


def test_fasthash_custom_algo_string_returns_algo_digest(
    fake: Faker,
    tmp_path: Path,
) -> None:
    """
    Given: a file and a custom algo passed by its required() import name.
    When: fasthash resolves "hashlib.sha1" instead of the default.
    Then: a 40-char sha1-style hexdigest unlike the default is returned.
    """
    # --- Arrange ---
    document = tmp_path / "blob.bin"
    document.write_bytes(fake.binary(length=DEFAULT_SAMPLE_SIZE))

    # --- Act ---
    custom = misc.fasthash(document, algo="hashlib.sha1")
    default = misc.fasthash(document)

    # --- Assert ---
    assert len(custom) == SHA1_HEX_LENGTH
    assert custom != default


def test_fasthash_unknown_algo_raises_import_error(
    fake: Faker,
    tmp_path: Path,
) -> None:
    """
    Given: a resolvable file and an unresolvable algo name.
    When: fasthash is called.
    Then: required() surfaces an ImportError naming the failed import.
    """
    # --- Arrange ---
    document = tmp_path / "blob.bin"
    document.write_bytes(fake.binary(length=DEFAULT_SAMPLE_SIZE))

    # --- Act / Assert ---
    with pytest.raises(ImportError, match="couldn't import required"):
        misc.fasthash(document, algo="no.such.algo")


# --- fasthash: tiny files (bugs/zx.lib/012 regression) ---


@pytest.mark.parametrize(
    "size",
    (0, 1, 2, 100),
    ids=("empty-file", "single-byte", "two-bytes", "sub-cluster"),
)
def test_fasthash_tiny_file_returns_stable_digest(
    tmp_path: Path,
    fake: Faker,
    size: int,
) -> None:
    """
    Given: a file too small for the cluster-sampling math.
    When: it is digested.
    Then: a stable digest is returned — no log2(0)/division by zero.
    """
    # --- Arrange ---
    document = tmp_path / "tiny.bin"
    document.write_bytes(fake.binary(length=size))

    # --- Act ---
    first = misc.fasthash(document)
    second = misc.fasthash(document)

    # --- Assert ---
    assert first == second
    assert len(first) == XXH128_HEX_LENGTH


def test_fasthash_tiny_files_of_different_size_differ(
    tmp_path: Path,
    fake: Faker,
) -> None:
    """
    Given: two tiny files differing only in size.
    When: both are digested.
    Then: the digests differ — the size participates in the digest.
    """
    # --- Arrange ---
    small = tmp_path / "small.bin"
    smaller = tmp_path / "smaller.bin"
    small.write_bytes(fake.binary(length=2))
    smaller.write_bytes(fake.binary(length=1))

    # --- Act / Assert ---
    assert misc.fasthash(small) != misc.fasthash(smaller)


def test_fasthash_tiny_same_size_different_content_differ(
    tmp_path: Path,
) -> None:
    """
    Given: two single-byte files whose only byte differs.
    When: both are digested.
    Then: the digests differ — tiny-file content participates in the digest.
    """
    # --- Arrange ---
    left = tmp_path / "left.bin"
    right = tmp_path / "right.bin"
    left.write_bytes(b"\x00")
    right.write_bytes(b"\x01")

    # --- Act / Assert ---
    assert misc.fasthash(left) != misc.fasthash(right)


def test_fasthash_tiny_file_custom_algo_returns_algo_digest(
    tmp_path: Path,
) -> None:
    """
    Given: a single-byte file and a custom algo resolved via required().
    When: fasthash takes the tiny-file branch with "hashlib.sha1".
    Then: a 40-char sha1-style hexdigest unlike the default is returned.
    """
    # --- Arrange ---
    document = tmp_path / "tiny.bin"
    document.write_bytes(b"\x2a")

    # --- Act ---
    custom = misc.fasthash(document, algo="hashlib.sha1")
    default = misc.fasthash(document)

    # --- Assert ---
    assert len(custom) == SHA1_HEX_LENGTH
    assert custom != default


# --- is_python_runtime ---


def test_is_python_runtime_real_interpreter_returns_true() -> None:
    """
    Given: the real running interpreter.
    When: is_python_runtime is called.
    Then: True is returned.
    """
    # --- Arrange ---

    # --- Act ---
    result = misc.is_python_runtime()

    # --- Assert ---
    assert result is True


def test_is_python_runtime_missing_executable_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: sys.executable pointing at a path that does not exist.
    When: is_python_runtime is called.
    Then: False is returned.
    """
    # --- Arrange ---
    monkeypatch.setattr(sys, "executable", "/nonexistent/runtime/python")

    # --- Act ---
    result = misc.is_python_runtime()

    # --- Assert ---
    assert result is False


# --- edge cases: fault pins and degenerate inputs ---


def test_fasthash_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    """
    Given: a path pointing at a file that does not exist.
    When: fasthash stats it.
    Then: a FileNotFoundError is raised before any hashing begins.
    """

    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(FileNotFoundError):
        misc.fasthash(tmp_path / "absent.bin")


def test_fasthash_directory_raises_is_a_directory(tmp_path: Path) -> None:
    """
    Given: a path pointing at an existing directory.
    When: fasthash opens it for reading.
    Then: an IsADirectoryError is raised.

    pin: current behavior — stat() on a directory succeeds, so the fault
    surfaces only at open().
    """

    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(IsADirectoryError):
        misc.fasthash(tmp_path)


def test_fasthash_str_path_matches_path_object(
    fake: Faker,
    tmp_path: Path,
) -> None:
    """
    Given: one file referenced by both a str path and a Path object.
    When: both are digested.
    Then: the digests are identical — the path type is transparent.
    """

    # --- Arrange ---
    document = tmp_path / "blob.bin"
    document.write_bytes(fake.binary(length=DEFAULT_SAMPLE_SIZE))

    # --- Act ---
    from_str = misc.fasthash(str(document))
    from_path = misc.fasthash(document)

    # --- Assert ---
    assert from_str == from_path
    assert len(from_str) == XXH128_HEX_LENGTH


def test_cycler_empty_sequence_raises_stop_iteration() -> None:
    """
    Given: an empty input sequence.
    When: the first value is drawn from the cycler.
    Then: StopIteration is raised — the degenerate input is not guarded.

    pin: current behavior, flagged — an empty sequence raises on first use.
    """

    # --- Arrange ---
    draw = misc.cycler(())

    # --- Act / Assert ---
    with pytest.raises(StopIteration):
        draw()


def test_shuffler_equal_distinct_items_boundary_guard_uses_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a shuffler over three items where two are equal by value but
        distinct by identity, and a scripted shuffle order whose second
        permutation would repeat the boundary value.
    When: two full batches are drawn.
    Then: the rejected permutation is skipped and the next one is drawn —
        the boundary guard compares equality, not identity.
    """
    # --- Arrange ---
    first: list[int] = [7]
    second: list[int] = [7]
    items = (first, second, "c")
    permutations = iter(
        (
            [items[2], first, second],
            [first, items[2], second],
            [items[2], second, first],
        ),
    )

    def scripted_shuffle(array: list[object]) -> None:
        array[:] = next(permutations)

    monkeypatch.setattr(misc, "shuffle", scripted_shuffle)
    draw = misc.shuffler(items)

    # --- Act ---
    head = tuple(draw() for _ in range(len(items)))
    tail = tuple(draw() for _ in range(len(items)))

    # --- Assert ---
    assert head == (items[2], first, second)
    assert tail == (items[2], second, first)


def test_set_title_empty_title_falls_back_to_argv(
    title_recorder: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an empty-string title and a .py argv[0].
    When: set_title is called.
    Then: the falsy title is ignored and the argv stem is used.

    pin: current behavior — an empty title silently falls back to argv.
    """

    # --- Arrange ---
    monkeypatch.setattr(sys, "argv", ["/opt/app/tool.py", "--flag", "value"])

    # --- Act ---
    misc.set_title("")

    # --- Assert ---
    assert title_recorder == ["tool"]
