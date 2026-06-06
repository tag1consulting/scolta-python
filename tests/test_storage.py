"""Ported from tests/Storage/FilesystemDriverTest.php (1:1).

PHP raises \\InvalidArgumentException for stream wrappers; the Python port
raises ValueError (the closest builtin) with the same "Stream wrappers" message.
"""

import os

import pytest

from scolta.storage import FilesystemDriver


@pytest.fixture
def driver():
    return FilesystemDriver()


@pytest.fixture
def tmp(tmp_path):
    return str(tmp_path)


def test_put_and_get(driver, tmp):
    path = os.path.join(tmp, "test.txt")
    assert driver.put(path, "hello") is True
    assert driver.get(path) == "hello"


def test_exists(driver, tmp):
    path = os.path.join(tmp, "exists.txt")
    assert driver.exists(path) is False
    driver.put(path, "data")
    assert driver.exists(path) is True


def test_delete(driver, tmp):
    path = os.path.join(tmp, "delete.txt")
    driver.put(path, "data")
    assert driver.delete(path) is True
    assert driver.exists(path) is False


def test_make_directory(driver, tmp):
    d = os.path.join(tmp, "sub", "nested")
    assert driver.make_directory(d) is True
    assert os.path.isdir(d)


def test_move(driver, tmp):
    src = os.path.join(tmp, "from.txt")
    dst = os.path.join(tmp, "to.txt")
    driver.put(src, "moved")
    assert driver.move(src, dst) is True
    assert driver.exists(src) is False
    assert driver.get(dst) == "moved"


def test_files(driver, tmp):
    driver.put(os.path.join(tmp, "a.txt"), "1")
    driver.put(os.path.join(tmp, "b.txt"), "2")
    assert len(driver.files(tmp, "*.txt")) == 2


def test_delete_directory(driver, tmp):
    d = os.path.join(tmp, "toremove")
    os.mkdir(d)
    driver.put(os.path.join(d, "file.txt"), "data")
    assert driver.delete_directory(d) is True
    assert not os.path.isdir(d)


def test_put_creates_parent_directories(driver, tmp):
    path = os.path.join(tmp, "deep", "nested", "dir", "file.txt")
    assert driver.put(path, "deep") is True
    assert driver.get(path) == "deep"


def test_rejects_stream_wrappers(driver):
    for wrapper in (
        "php://filter/resource=/etc/passwd",
        "file:///etc/passwd",
        "expect://ls",
    ):
        with pytest.raises(ValueError, match="Stream wrappers"):
            driver.get(wrapper)


def test_rejects_stream_wrapper_in_put(driver):
    with pytest.raises(ValueError, match="Stream wrappers"):
        driver.put("php://memory", "data")


def test_rejects_stream_wrapper_in_move(driver):
    with pytest.raises(ValueError, match="Stream wrappers"):
        driver.move("php://filter/resource=/etc/passwd", "/tmp/out")


def test_normal_paths_are_not_rejected(driver, tmp):
    path = os.path.join(tmp, "normal-file.txt")
    driver.put(path, "ok")
    assert driver.get(path) == "ok"
