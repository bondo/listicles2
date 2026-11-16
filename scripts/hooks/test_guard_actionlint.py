"""The allow rules would approve actionlint -shellcheck/-pyflakes (run any executable), -init-config and zizmor --fix (rewrite
.github/), --cache-dir; the guard denies them in every spelling and wrapper, and shell syntax that could expand into them
(reviews R1-01, R2-01, R3-01..R3-04)."""

import unittest

from test_pretooluse_guard import repo, run

A = ".tools/bin/actionlint"
Z = ".tools/bin/zizmor --offline"
HOSTILE = [
    f"{A} -shellcheck=./x.sh .github/workflows/ci.yml", f"{A} -shellcheck ./x.sh f.yml", f"{A} --shellcheck=./x.sh f.yml",
    f"{A} --shellcheck ./x.sh f.yml", f"{A} -pyflakes=/bin/sh f.yml", f"{A} -pyflakes /bin/sh f.yml", f"{A} --pyflakes=./x f.yml",
    f"{A} -shellcheck= -shellcheck=./x.sh f.yml", f"{A} -shellcheck=.tools/bin/shellcheck -pyflakes= -pyflakes=./x f.yml",
    f"{A} f.yml -shellcheck=./x.sh", f"{A} -color -shellcheck=./x.sh f.yml", f"{A} '-shellcheck=./x.sh' f.yml",
    f'{A} "-pyflakes=./x" f.yml', f'{A} -shell""check=./x f.yml', f"{A} -shell\\check=./x f.yml", f"{A} -init-config", f"{A} --init-config",
    "actionlint -shellcheck=./x.sh f.yml", f"/home/user/listicles2/{A} -shellcheck=./x f.yml", f"./{A} -pyflakes=./x f.yml",
    f"env X=1 {A} -shellcheck=./x f.yml", f"timeout 5 {A} -pyflakes=./x f.yml", f"nohup {A} -shellcheck=./x f.yml",
    f"echo f.yml | xargs {A} -shellcheck=./x", f"bash -c '{A} -shellcheck=./x f.yml'", f'sh -c "{A} -pyflakes=./x f.yml"',
    f"cd /tmp && {A} -pyflakes=./x f.yml", f"true; {A} -shellcheck=./x f.yml", f"find . -name '*.yml' -exec {A} -shellcheck=./x {{}} +",
    f"eval '{A} -shellcheck=./x f.yml'", f"{A} $(echo -shellcheck=./x) f.yml", f"{A} `echo -shellcheck=./x` f.yml", f"{A} $FLAG f.yml",
    f"{A} ${{FLAG}} f.yml", f"{A} -shellcheck=$X f.yml", f"F=-shellcheck=./x.sh; {A} $F f.yml",
    # R2-01: brace expansion and globs; R3-02: tilde, extglob, shopt; R3-04: coproc, find -exec glob; R3-01: zizmor flags
    f"{A} {{-shellcheck=./x,f.yml}}", f"{A} {{-pyflakes,/bin/sh}} f.yml", f"bash -c '{A} {{-shellcheck=./x,f.yml}}'", f"{A} -s*/x",
    f"{A} -?hellcheck=./x f.yml", f"{A} [-]shellcheck=./x f.yml", f"{A} {{,-shellcheck=./x}} f.yml", f"{A} {{{{-shellcheck=./x,a}},b}}",
    f"{A} '-s'*/x", f"{A} \\-s*/x", f"{A} -shellcheck={{a,b}}", f"{A} f.yml {{-pyflakes,x}}", f"eval '{A} -s*/x'",
    f"echo f | xargs {A} {{-pyflakes,x}}", f"{Z} --fix .github/workflows", f"{Z} --fix=all .github/workflows", f"{Z} --fix=safe .",
    f"{Z} --fix=unsafe-only .", f"{Z} --fix all .", f"{Z} .github/workflows --fix", f"{Z} -fix=all .", f"{Z} --cache-dir /tmp/x .",
    f"{Z} --cache-dir=/tmp/x .", f"{Z} --lsp", f"{Z} {{--fix,x}} .", f"{Z} --fix=$M .", f"env X=1 {Z} --fix .",
    f"echo . | xargs {Z} --fix=all", f"bash -c '{Z} --offline --fix=all .'", f"HOME=-shellcheck=./x; {A} ~ f.yml",
    f"OLDPWD=-pyflakes=/bin/sh; {A} ~- f.yml", f"{A} ~root/x", "shopt -s extglob", "shopt -s extglob; true",
    f"{A} @(-shellcheck=.)/x f.yml", f"{A} +(-shellcheck=.)/x f.yml", f"{A} !(f.yml)/x", f"coproc {A} -shellcheck=./x f.yml",
    f"find . -exec {A} -s*/x {{}} +",
]
ALLOWED = [
    A, f"{A} .github/workflows/ci.yml", f"{A} -color -oneline .github/workflows/ci.yml .github/workflows/other.yml",
    f"{A} -format '{{{{.Message}}}}' f.yml", f"{A} -ignore 'shellcheck reported' f.yml", f"{A} -config-file .github/actionlint.yaml f.yml",
    f"{A} -verbose f.yml 2>/dev/null", ".tools/bin/shellcheck -s bash scripts/verify.sh", ".tools/bin/zizmor --offline .github/workflows",
    "echo -shellcheck=./x", "grep -n -- -shellcheck docs/x.md", f"cat .github/workflows/ci.yml | {A} -stdin-filename ci.yml -",
    f"{A} .github/workflows/*.yml", f"{A} .github/workflows/ci.y?ml", f"{A} .github/workflows/[a-c]*.yml", f"{A} ./f{{1,2}}.yml",
    "PATH=/usr/bin true", f"{A} -format \"{{{{.Message}}}}\" f.yml", f"{Z} --format=plain .github/workflows", f"{Z} --format plain .", "shopt -s globstar",
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
