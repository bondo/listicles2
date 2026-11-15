"""actionlint runs the executable named by -shellcheck / -pyflakes and -init-config writes under .github/; the allow rule
Bash(.tools/bin/actionlint *) would approve them, so the guard denies them in every spelling and wrapper (review R1-01, PR #95)."""

import unittest

from test_pretooluse_guard import repo, run

HOSTILE = [
    ".tools/bin/actionlint -shellcheck=./x.sh .github/workflows/ci.yml",
    ".tools/bin/actionlint -shellcheck ./x.sh .github/workflows/ci.yml",
    ".tools/bin/actionlint --shellcheck=./x.sh f.yml",
    ".tools/bin/actionlint --shellcheck ./x.sh f.yml",
    ".tools/bin/actionlint -pyflakes=/bin/sh f.yml",
    ".tools/bin/actionlint -pyflakes /bin/sh f.yml",
    ".tools/bin/actionlint --pyflakes=./x f.yml",
    ".tools/bin/actionlint -shellcheck= -shellcheck=./x.sh f.yml",
    ".tools/bin/actionlint -shellcheck=.tools/bin/shellcheck -pyflakes= -pyflakes=./x f.yml",
    ".tools/bin/actionlint f.yml -shellcheck=./x.sh",
    ".tools/bin/actionlint -color -shellcheck=./x.sh f.yml",
    ".tools/bin/actionlint '-shellcheck=./x.sh' f.yml",
    '.tools/bin/actionlint "-pyflakes=./x" f.yml',
    '.tools/bin/actionlint -shell""check=./x f.yml',
    ".tools/bin/actionlint -shell\\check=./x f.yml",
    ".tools/bin/actionlint -init-config",
    ".tools/bin/actionlint --init-config",
    "actionlint -shellcheck=./x.sh f.yml",
    "/home/user/listicles2/.tools/bin/actionlint -shellcheck=./x f.yml",
    "./.tools/bin/actionlint -pyflakes=./x f.yml",
    "env X=1 .tools/bin/actionlint -shellcheck=./x f.yml",
    "timeout 5 .tools/bin/actionlint -pyflakes=./x f.yml",
    "nohup .tools/bin/actionlint -shellcheck=./x f.yml",
    "echo f.yml | xargs .tools/bin/actionlint -shellcheck=./x",
    "bash -c '.tools/bin/actionlint -shellcheck=./x f.yml'",
    "sh -c \".tools/bin/actionlint -pyflakes=./x f.yml\"",
    "cd /tmp && .tools/bin/actionlint -pyflakes=./x f.yml",
    "true; .tools/bin/actionlint -shellcheck=./x f.yml",
    "find . -name '*.yml' -exec .tools/bin/actionlint -shellcheck=./x {} +",
    "eval '.tools/bin/actionlint -shellcheck=./x f.yml'",
    ".tools/bin/actionlint $(echo -shellcheck=./x) f.yml",
    ".tools/bin/actionlint `echo -shellcheck=./x` f.yml",
    ".tools/bin/actionlint $FLAG f.yml",
    ".tools/bin/actionlint ${FLAG} f.yml",
    ".tools/bin/actionlint -shellcheck=$X f.yml",
    "F=-shellcheck=./x.sh; .tools/bin/actionlint $F f.yml",
]
ALLOWED = [
    ".tools/bin/actionlint",
    ".tools/bin/actionlint .github/workflows/ci.yml",
    ".tools/bin/actionlint -color -oneline .github/workflows/ci.yml .github/workflows/other.yml",
    ".tools/bin/actionlint -format '{{.Message}}' f.yml",
    ".tools/bin/actionlint -ignore 'shellcheck reported' f.yml",
    ".tools/bin/actionlint -config-file .github/actionlint.yaml f.yml",
    ".tools/bin/actionlint -verbose f.yml 2>/dev/null",
    ".tools/bin/shellcheck -s bash scripts/verify.sh",
    ".tools/bin/zizmor --offline .github/workflows",
    "echo -shellcheck=./x",
    "grep -n -- -shellcheck docs/x.md",
    "cat .github/workflows/ci.yml | .tools/bin/actionlint -stdin-filename ci.yml -",
]


class ActionlintFlags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = repo()

    def test_hostile_forms_denied_in_every_session_kind(self):
        for c in HOSTILE:
            for env in (None, {"LISTICLES_TASK": "tooling"}):
                self.assertEqual(run("Bash", {"command": c}, self.d, env), 2, (c, env))

    def test_normal_use_allowed(self):
        for c in ALLOWED:
            self.assertEqual(run("Bash", {"command": c}, self.d), 0, c)


if __name__ == "__main__":
    unittest.main()
