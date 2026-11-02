"""Generated, public test corpus; no external course content is required."""
import json
import os
from pathlib import Path
import tempfile

# Keep the corpus alive for module-level acceptance fixtures, then remove it at exit.
_TEMP = tempfile.TemporaryDirectory(prefix='synthetic-library-')

def source():
    configured = os.environ.get('SHUYU_LIBRARY_SOURCE')
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_dir():
            raise ValueError('SHUYU_LIBRARY_SOURCE must be an existing library directory')
        return path
    root = Path(_TEMP.name)
    articles = root / 'articles'
    if articles.exists():
        return root
    articles.mkdir()
    catalog = {'date': 'synthetic-fixture', 'shared_entry': ['BASE-002'],
               'effective_articles': 130, 'tracks': [], 'articles': []}
    for prefix, count in [('MON', 77), ('EDU', 52)]:
        groups = []
        for index in range(6):
            identifiers = [f'{prefix}-{n:03d}' for n in range(1, count + 1) if (n-1) % 6 == index]
            group_id = f'{prefix}-group-{index}'
            groups.append({'id': group_id, 'title': f'Synthetic group {index}',
                           'article_ids': identifiers,
                           'sections': [{'label': 'Synthetic section', 'article_ids': identifiers}]})
            for identifier in identifiers:
                catalog['articles'].append({'id': identifier, 'href': f'articles/{identifier}.md',
                    'version': 'synthetic-v1', 'primary_track': prefix, 'primary_group': group_id})
        catalog['tracks'].append({'id': prefix, 'title': f'Synthetic {prefix}',
            'group_count': 6, 'primary_article_count': count, 'groups': groups})
    catalog['articles'].append({'id': 'BASE-002', 'href': 'articles/BASE-002.md',
                               'version': 'synthetic-v1', 'primary_track': 'shared'})
    for record in catalog['articles']:
        identifier = record['id']
        # Multiple packed blocks exercise full text reconstruction and tail search.
        text = f'---\nstableID: {identifier}\n---\n# Synthetic article {identifier}\n'
        text += ''.join(f'Synthetic {identifier} sample line {n:03d}: ' + 'abcdef ' * 12 + '\n' for n in range(65))
        text += f'Unique synthetic tail {identifier}\n'
        (root / record['href']).write_text(text, encoding='utf-8')
    (root / 'topic_map.json').write_text(json.dumps(catalog), encoding='utf-8')
    return root
