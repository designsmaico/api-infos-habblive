import unittest
from app import parse_payload


def fixture(name='Teste', badge='VIP'):
    return f'''<div id="blauw01">Perfil de {name}</div><table><tr><td>
    <img alt="Avatar de {name}" src="https://habbo.city/habbo-imaging/avatarimage?figure=hd-1&amp;size=l">
    </td><td><b>ID:</b> 358<br><b>Miss&atilde;o:</b> Olá &amp; amigos<br>
    <b>Placar de Conquistas:</b> 33.285<br><b>Gemas:</b> 0<br></td></tr></table>
    <div class="perfil-badge" style="background-image:url('//images.habblive.com/c_imagenes/album1584/{badge}.gif')"></div>
    <a href="/perfil?user={name}&amp;badge_page=2">Próxima</a>'''


class ProfileTests(unittest.TestCase):
    def test_fields_entities_and_images(self):
        p = parse_payload({'html': fixture()})
        self.assertEqual(p['motto'], 'Olá & amigos')
        self.assertEqual(p['achievement_score'], 33285)
        self.assertEqual(p['gems'], 0)
        self.assertEqual(p['figure'], 'hd-1')
        self.assertEqual(p['pagination']['other_pages'], [2])
        self.assertEqual(p['badges'][0]['code'], 'VIP')

    def test_merge_and_deduplicate(self):
        p = parse_payload({'pages': [fixture(), fixture(badge='RHCOORD'), fixture()]})
        self.assertEqual([b['code'] for b in p['badges']], ['VIP', 'RHCOORD'])

    def test_reject_login_and_mixed_users(self):
        for payload in ({'html': '<h1>Entrar no Habblive</h1>'},
                        {'pages': [fixture(), fixture(name='Outro')]}, {'pages': []}):
            with self.assertRaises(ValueError):
                parse_payload(payload)

    def test_reject_untrusted_image_origin(self):
        p = parse_payload({'html': fixture().replace('https://habbo.city/', 'https://example.com/')})
        self.assertIsNone(p['avatar_url'])
        self.assertIsNone(p['figure'])


if __name__ == '__main__':
    unittest.main()
