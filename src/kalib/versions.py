from contextlib import suppress
from os import walk
from pathlib import Path
from re import match

from kalib.datastructures import json
from kalib.descriptors import Property, cache
from kalib.importer import optional, required, sort
from kalib.internals import Who, iter_stack, sourcefile
from kalib.loggers import Logging
from kalib.misc import is_python_runtime

DEFAULT_VERSION_RE = r'^(v\d+\.py)$'

logger = Logging.Default


class Git(Logging.Mixin):

    @Property.Class.Cached
    def Repo(cls):  # noqa: N802
        return required('git.Repo')

    @Property.Class.Parent
    def root(cls):
        expect = suppress(required('git.exc.InvalidGitRepositoryError', quiet=True))
        with expect, cls.Repo(
            Path.cwd().resolve(),
            search_parent_directories=True,
        ) as repo:
            return Path(repo.working_tree_dir).resolve()
        cls.log.verbose('not detected')

    @Property.Class.Parent
    def repo(cls):
        if (path := cls.root):
            return cls.Repo(path, search_parent_directories=True)
        cls.log.verbose('not found')

    @Property.Class.Parent
    def from_path(cls):
        root = cls.root

        if not root:
            cls.log.warning("feature disabled, git root isn't detected")
            return (lambda *args: None)  # noqa: ARG005

        @cache
        def resolver(path):
            for commit in cls.repo.iter_commits(paths=path, max_count=1):
                return commit
            cls.log.warning(f'{path=} not in repository {root!s} index')

        @cache
        def explorer(path):
            file = Path(path).resolve()

            if not file.is_file():
                cls.log.warning(f'{path=} ({file!s}) not found')
                return

            elif not str(file).startswith(str(root)):
                cls.log.warning(f'{path=} ({file!s}) not in {root!s}')
                return

            return resolver(str(file)[len(str(root)) + 1:])

        return explorer

    @Property.Class.Parent
    def files(cls):
        result = []
        prefix = len(str(cls.root)) + 1
        for rt, _, fs in walk(cls.root):
            root = Path(rt)
            for f in fs:
                if f.endswith('.py'):
                    result.append(str(root / f)[prefix:])

        return tuple(sort(result))

    @Property.Class.Parent
    def tree(cls):
        return {
            path: str(cls.from_path(path)) for path in cls.files
            if cls.from_path(path) is not None}

    @Property.Class.Parent
    def tag(cls):
        with suppress(Exception), cls.repo as git:
            head = git.head.commit

            def get_distance(tag):
                return int(cli.rev_list(
                    '--count', f'{tag.commit.hexsha}..{head.hexsha}'))

            if git.tags:
                cli = required('git.Git')()
                distances = {
                    tag: get_distance(tag)
                    for tag in sort(git.tags, key=lambda x: x.name, reverse=True)}

                if distances:
                    return sorted(distances, key=lambda x: distances[x])[0]

    @Property.Class.Parent
    def version(cls):
        with suppress(ImportError):
            if cls.tag and (version := optional('versioneer.get_version')):
                return version()


@cache
def latest(name, path, pattern=None):
    files = tuple(filter(
        lambda x: match(pattern or DEFAULT_VERSION_RE, x.name),
        Path(path).parent.glob('*.py')))

    if files:
        version = Path(sort(files)[-1]).stem
        module = getattr(__import__(name, globals(), locals(), [version]), version)
        logger.verbose(f'{name} {module=}')
        return module


def add_versioned_path(pattern=None):
    """Add the latest versioned module to the caller's namespace."""

    if not is_python_runtime():
        raise NotImplementedError('this function is for python runtime only')

    def get_call_frame():
        """Get the frame of the caller of the function that called this
        function."""
        for frame in iter_stack(offset=2):
            if frame.filename == __file__:  # skip self
                continue
            if frame.code_context is not None:
                return frame
        raise IndexError

    try:
        pointer = get_call_frame()

    except IndexError:
        raise RuntimeError('could not find the caller frame') from None

    local  = pointer.frame.f_locals
    module = latest(local['__name__'], pointer.filename, pattern)

    to_import = getattr(module, '__all__', ())
    if isinstance(to_import, str):
        # we can override and use as __all__ == 'EntityName'
        to_import = (to_import,)

    local['latest'] = module
    for something in to_import:
        try:
            local[something] = getattr(module, something)

        except AttributeError:

            msg = (
                f"couldn't import {something!a} from module {Who.Name(module)!a}; "
                f"may be it's not found, but declared in {Who.Name(module)}.__all__ = "
                f'{json.repr(to_import)} in {sourcefile(module)!r}')

            logger.critical(msg)
            raise ImportError(msg) from None

    return module
