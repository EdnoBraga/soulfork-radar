"""A busca para de pedir páginas ao Google assim que junta a quantidade pedida.
Roda sem rede: o PlacesClient é trocado por um falso que conta as páginas."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prospector import pipeline


class PlacesFalso:
    paginas = 0

    def __init__(self, chave):
        self.chamadas = 0

    def buscar(self, texto, max_resultados=60, tipo=None):
        entregues = 0
        for pagina in range(3):                      # 3 páginas de 20, como a API
            self.chamadas += 1
            PlacesFalso.paginas += 1
            for i in range(20):
                # termos diferentes repetem metade das empresas
                yield {"id": f"{i if i % 2 else texto}-{pagina}-{i}",
                       "displayName": {"text": f"{texto} {pagina}-{i}"}}
                entregues += 1
                if entregues >= max_resultados:
                    return


pipeline.PlacesClient = PlacesFalso
pipeline.enriquecer = lambda lead, *a, **k: lead      # sem visitar sites


def rodar(quantidade, termos):
    PlacesFalso.paginas = 0
    stats = {}
    leads = pipeline.rodar("x", termos, "Brasília, DF", chave_places="k",
                           max_por_termo=min(quantidade, 60), limite_total=quantidade,
                           stats=stats, paralelismo=1)
    return leads, stats


leads, stats = rodar(20, ["a", "b", "c"])
assert len(leads) == 20, len(leads)
assert PlacesFalso.paginas == 1 and stats["chamadas"] == 1, (PlacesFalso.paginas, stats)

leads, stats = rodar(21, ["a", "b"])
assert len(leads) == 21, len(leads)
assert stats["chamadas"] == 2, stats                 # a 2ª página só porque faltou 1

leads, stats = rodar(80, ["a", "b"])
assert len(leads) == 80, len(leads)
assert stats["chamadas"] == 5, stats                 # 3 do termo a + 2 do b (10 inéditas por página)

leads, stats = rodar(120, ["a", "b"])
assert len(leads) == 90, len(leads)                  # acabaram os termos: entrega o que achou

leads, stats = rodar(20, ["a"])
assert [l.posicao_maps for l in sorted(leads, key=lambda l: l.posicao_maps)][:3] == [1, 2, 3]

print("✓ busca: para no limite e conta as chamadas")
