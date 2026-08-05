from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_marca_visivel_usa_orkavyn_agro_intelligence():
    arquivos = [
        ROOT / 'templates' / 'index.html',
        ROOT / 'templates' / 'landing.html',
        ROOT / 'templates' / 'login.html',
        ROOT / 'templates' / 'cadastro.html',
        ROOT / 'templates' / 'register.html',
        ROOT / 'templates' / 'admin.html',
        ROOT / 'templates' / 'termos.html',
        ROOT / 'templates' / 'privacidade.html',
    ]
    texto = '\n'.join(path.read_text(encoding='utf-8') for path in arquivos)

    assert 'Orkavyn Agro Intelligence' in texto
    assert 'BovCredit' not in texto
