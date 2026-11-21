# -*- coding: utf-8 -*-
"""The conduct gate on the incoming webhook.

`sales_automation` calls `_sa_conduct_gate` once the text and sender of an
incoming message are known and before anything reads it. Its own version
says "not handled". This one checks the list, and when a word hits, records
the message as blocked, remarks the sender, deletes it in WhatsApp, warns,
and re-scores - then says "handled" so no enquiry, quote or reply is made of it.

Only in the groups linked under Sales Groups (enabled), and in private chats
to the shop; every other group the number belongs to is left alone.
"""
import logging

from odoo.addons.sales_automation.controllers.group_webhook import WhatsAppWebhookGroups
from odoo.http import request

_logger = logging.getLogger(__name__)


class ConductWebhook(WhatsAppWebhookGroups):

    def _sa_conduct_gate(self, session, data, key, remote_jid, text,
                         participant, participant_lid):
        env = request.env
        settings = env['sa.ai.settings'].sudo().get_settings()
        if not settings or not settings.conduct_enabled:
            return False
        # Only the shop's own groups - the ones linked and ticked under Sales
        # Groups on this number. The number also sits in family, college and
        # job groups; removing, remarking and warning people there is none of
        # the shop's business. Private chats to the shop number are its own.
        if str(remote_jid).endswith('@g.us') and not env['sa.sales.group'].sudo().search_count([
                ('session_id', '=', session.id), ('group_jid', '=', remote_jid),
                ('enabled', '=', True)], limit=1):
            return False
        Remark = env['sa.conduct.remark'].sudo()
        message = data.get('message') or {}
        text = text or ''
        hits, hit_type = [], 'word'
        decided_by, confidence, reason = 'local', 100, ''
        kind, node = Remark.media_node(message)
        # Media carries its own words: caption and file name count as text.
        local_text = text
        if node is not None:
            extra = ' '.join(str(node.get(k) or '') for k in ('caption', 'fileName', 'title'))
            local_text = (text + ' ' + extra).strip()

        # Tier 1 - the local list: certain, no model.
        if local_text.strip():
            hits = Remark.match_words(local_text, settings)
            if not hits:
                hits = Remark.match_links(local_text, settings)
                hit_type = 'link'

        # Tier 2 - doubt: ask the model, and only then.
        doubt_score, doubt_why = (0, [])
        ask_later = None
        if not hits and local_text.strip():
            doubt_score, doubt_why = Remark.find_doubt(local_text, settings)
            if settings.conduct_model_mode == 'all' and doubt_score < 50:
                doubt_score, doubt_why = 50, doubt_why or ['every message']
            if doubt_score >= max(1, settings.conduct_doubt_min or 50):
                near = [w for w in doubt_why if '~' in w]
                hint = '; '.join('"%s" looks like the banned word "%s"' % tuple(w.split('~', 1))
                                 for w in near)
                if getattr(settings, 'conduct_doubt_action', 'delete_first') == 'delete_first' \
                        and settings.conduct_model_mode != 'all':
                    # Removed now; the model grades the remark afterwards
                    # (see the tail of this method). Waiting for it left a
                    # rude word in the group for the whole model timeout.
                    hits, hit_type = ['doubt: %s' % ', '.join(doubt_why)], 'doubt'
                    decided_by, confidence = 'local', doubt_score
                    ask_later = (local_text, hint)
                    verdict = 'later'
                else:
                    verdict = Remark.classify_text(local_text, settings, hint=hint)
                if verdict == 'later':
                    pass
                elif verdict is None:
                    # Doubtful and nobody to ask: removed, as the owner asked.
                    hits, hit_type = ['doubt: %s' % ', '.join(doubt_why)], 'doubt'
                    decided_by, confidence = 'model_down', doubt_score
                else:
                    abusive, conf, reason = verdict
                    if abusive and conf >= (settings.conduct_llm_min_confidence or 60):
                        hits, hit_type = ['doubt: %s' % ', '.join(doubt_why)], 'doubt'
                        decided_by, confidence = 'model', conf
                    else:
                        _logger.info("Conduct: doubtful but kept (%s, model %s%% %s): %r",
                                     ', '.join(doubt_why), conf, reason, local_text[:60])

        # Tier 3 - pictures and videos: always the model; when it is down,
        # removed only if the words around it already looked wrong.
        if not hits and node is not None and settings.conduct_media:
            b64, mime = Remark.picture_of(session, data, kind, node, self._fetch_media)
            if b64:
                verdict = Remark.classify_image(b64, mime, settings)
                if verdict is None and doubt_score >= max(1, settings.conduct_doubt_min or 50):
                    hits, hit_type = ['doubt: %s %s' % (kind, ', '.join(doubt_why))], 'media'
                    decided_by, confidence = 'model_down', doubt_score
                elif verdict:
                    hits, hit_type = ['sexual %s' % kind], 'media'
                    decided_by, confidence = 'model', 100
            if hits and not text.strip():
                text = '[%s]%s' % (kind, (' ' + local_text) if local_text.strip() else '')
        if not hits:
            return False

        is_group = str(remote_jid).endswith('@g.us')
        digits = ''.join(ch for ch in str(participant or '') if ch.isdigit())
        wa_id = str(key.get('id') or '')

        # The record stays, marked blocked, so the thread shows a message was
        # removed here; the text itself is on the remark.
        vals = {
            'session_id': session.id,
            'phone': remote_jid if is_group else digits,
            'message': '[removed: %s]' % ', '.join(hits),
            'direction': 'incoming',
            'status': 'blocked',
            'wa_message_id': wa_id,
            'push_name': str(data.get('pushName') or ''),
        }
        if is_group:
            vals.update({
                'group_jid': remote_jid,
                'participant_phone': participant or '',
                'participant_lid': participant_lid or '',
                'participant_is_lid': bool(participant_lid and not digits),
            })
        msg = env['whatsapp.message'].sudo().create(vals)

        remark = Remark.create({
            'kind': Remark._kind_for(digits, is_group, remote_jid if is_group else ''),
            'source': 'auto',
            'phone': digits,
            'lid': participant_lid or '',
            'participant_jid': str(key.get('participant') or '') if is_group else '',
            'session_id': session.id,
            'group_jid': remote_jid if is_group else '',
            'wa_message_id': wa_id,
            'message_id': msg.id,
            'text': text,
            'matched_words': ', '.join(hits),
            'hit_type': hit_type,
            'decided_by': decided_by,
            'confidence': confidence,
            'reason': reason,
            'severity': 'high' if (len(hits) > 1 or hit_type == 'media') else 'normal',
        })
        _logger.info("Conduct: removed %s from %s in %s (%s)",
                     wa_id, digits or participant_lid or '?', remote_jid,
                     ', '.join(hits))
        remark._try_delete()
        remark._try_warn(settings.conduct_warn or 'off',
                         settings.conduct_warn_text or '')
        if ask_later:
            # The message is gone; this only grades the remark, so a model
            # that disagrees lowers its weight instead of restoring anything.
            try:
                verdict = Remark.classify_text(ask_later[0], settings, hint=ask_later[1])
            except Exception as err:  # noqa: BLE001 - never 500 the webhook
                _logger.info("Conduct: late model grade failed: %s", err)
                verdict = None
            if verdict is not None:
                abusive, conf, reason = verdict
                vals = {'decided_by': 'model', 'confidence': conf, 'reason': reason}
                if not (abusive and conf >= (settings.conduct_llm_min_confidence or 60)):
                    vals.update({'note': 'Removed on the local doubt score; the model '
                                         'did not call it abusive (%s%%).' % conf})
                try:
                    remark.write(vals)
                except Exception as err:  # noqa: BLE001
                    _logger.info("Conduct: could not grade remark %s: %s", remark.id, err)
        try:
            # A savepoint: two fast messages re-scoring the same row can
            # collide, and without it that error poisons the whole request
            # and the remark is lost after the delete already happened.
            with env.cr.savepoint():
                env['sa.insight.entity'].sudo()._attach_remark(remark)
        except Exception as err:  # noqa: BLE001 - a rating is not worth a 500
            _logger.warning("Conduct: could not attach remark %s: %s", remark.id, err)
        return True
