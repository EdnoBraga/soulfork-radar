"""Ponto de entrada do executável empacotado (PyInstaller).

Sobe o servidor local, abre o navegador e grava log na pasta do usuário
(o app roda sem janela de console — sem log em arquivo, erro vira mistério).
"""
import sys
import traceback


def main() -> int:
    from prospector import config

    log_path = config.pasta_dados() / "radar.log"
    try:
        log = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = log
        sys.stderr = log
    except OSError:
        pass

    try:
        from prospector.web.app import main as web_main
        web_main()
        return 0
    except OSError as e:
        # porta ocupada = provavelmente o Radar já está aberto
        if getattr(e, "errno", None) in (48, 98, 10048) or "10048" in str(e):
            import webbrowser
            webbrowser.open("http://localhost:8760")
            return 0
        traceback.print_exc()
        return 1
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
