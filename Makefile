.PHONY: default help install lint test

help:
	@just default

install:
	@mise trust --yes mise.toml
	@mise install

lint:
	@uv run --quiet \
	  pre-commit run \
	--config etc/pre-commit.yaml \
	--all

test:
	@PYTHONASYNCIODEBUG=1 \
	uv run --quiet \
	pytest \
		-rs \
		-svvv \
		--cov app \
		--cov-report term-missing

%:
	@just $@

.DEFAULT_GOAL := default
