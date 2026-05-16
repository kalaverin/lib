.PHONY: check default help install lint test

help:
	@just default

install:
	@mise trust --yes mise.toml
	@mise install

lint:
	@uv run --quiet \
		black \
		--quiet \
		--line-length 79 \
		--target-version py312 \
	'src/' 'tests/' \
	|| true

	@uv run --quiet \
		ruff check \
			--quiet \
			--fix \
		'src/' 'tests/' \
		|| true

	@uv run --quiet \
		yamlfix \
			--config-file etc/lint/yamlfix.toml \
			--exclude '.*/**/*.yml' \
			--exclude '.*/**/*.yaml' \
		. \
		|| true

check:
	@uv run --quiet \
		pre-commit run \
	--config etc/pre-commit.yaml \
	--all

stubs:
	@make clean-stubs || true
	@uv run --quiet righttyper \
	  --verbose \
	--python-version 3.12 \
		--generate-stubs \
		--overwrite \
		--replace-dict \
		--target-overhead 15 \
		--use-top-pct 90 \
		--srcdir src/kain \
		src/kain/__init__.py || true
	@cat righttyper.log righttyper.out || true
	@rm righttyper.log righttyper.out || true

	@rm src/kain/classes.pyi.bak 2>/dev/null || true
	@rm src/kain/importer.pyi.bak 2>/dev/null || true
	@rm src/kain/internals.pyi.bak 2>/dev/null || true
	@rm src/kain/properties/__init__.pyi.bak 2>/dev/null || true
	@rm src/kain/properties/cached/instance.pyi.bak 2>/dev/null || true
	@rm src/kain/properties/cached/klass.pyi.bak 2>/dev/null || true
	@rm src/kain/properties/cached/mixed.pyi.bak 2>/dev/null || true
	@rm src/kain/properties/cached/post.pyi.bak 2>/dev/null || true
	@rm src/kain/properties/cached/pre.pyi.bak 2>/dev/null || true
	@rm src/kain/properties/class_property.pyi.bak 2>/dev/null || true
	@rm src/kain/properties/primitives.pyi.bak 2>/dev/null || true


clean-stubs:
	@rm src/kain/classes.pyi 2>/dev/null || true
	@rm src/kain/importer.pyi 2>/dev/null || true
	@rm src/kain/internals.pyi 2>/dev/null || true
	@rm src/kain/properties/__init__.pyi 2>/dev/null || true
	@rm src/kain/properties/cached/instance.pyi 2>/dev/null || true
	@rm src/kain/properties/cached/klass.pyi 2>/dev/null || true
	@rm src/kain/properties/cached/mixed.pyi 2>/dev/null || true
	@rm src/kain/properties/cached/post.pyi 2>/dev/null || true
	@rm src/kain/properties/cached/pre.pyi 2>/dev/null || true
	@rm src/kain/properties/class_property.pyi 2>/dev/null || true
	@rm src/kain/properties/primitives.pyi 2>/dev/null || true

test:
	@PYTHONASYNCIODEBUG=1 \
	uv run --quiet \
	pytest \
		-rs \
		-svvv \
		--cov src \
		--cov-report term-missing

%:
	@just $@

