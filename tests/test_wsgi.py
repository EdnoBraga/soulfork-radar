"""wsgi.py de produção: recusa subir aberto e liga cookie seguro atrás do proxy."""
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def importar(env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIND_")}
    env.update(env_extra, PYTHONPATH=RAIZ, FIND_DADOS=os.path.join(RAIZ, "saida", "teste_wsgi"))
    codigo = ("import wsgi; c = wsgi.app.test_client();"
              "r = c.post('/entrar', data={'senha': 'uma-senha-longa'},"
              " headers={'X-Forwarded-Proto': 'https'});"
              "print(r.status_code, 'Secure' in r.headers.get('Set-Cookie', ''),"
              " c.get('/saude').text)")
    return subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=env,
                          capture_output=True, text=True)


r = importar({})
assert r.returncode != 0 and "FIND_SENHA" in r.stderr, r.stderr

r = importar({"FIND_SENHA": "curta", "FIND_SECRET_KEY": "x" * 40})
assert r.returncode != 0 and "FIND_SENHA" in r.stderr, "aceitou senha curta"

r = importar({"FIND_SENHA": "uma-senha-longa", "FIND_SECRET_KEY": "x" * 40})
assert r.returncode == 0, r.stderr
assert r.stdout.split() == ["302", "True", "ok"], r.stdout

print("✓ wsgi: não sobe aberto, cookie seguro, saúde pública")
