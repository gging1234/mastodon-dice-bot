#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""마스토돈 주사위 봇: GitHub Actions에서 한 번 실행한 뒤 종료합니다."""

import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from mastodon import Mastodon

BASE = 'https://planet.moe'
FORTUNE_FILE = Path(__file__).with_name('fortune_messages.txt')
# 서버 문제로 실행이 지연되어도 최근 24시간 내 멘션을 처리합니다.
# 24시간보다 오래된 멘션에는 답장하지 않습니다.
LOOKBACK_MINUTES = 1440


def make_reply(toot_html):
    """대괄호 명령을 분석해 답장 내용을 만듭니다. 명령이 없으면 빈 문자열 반환."""
    toot_text = BeautifulSoup(toot_html or '', 'html.parser').get_text(' ', strip=True)
    left = toot_text.find('[')
    right = toot_text.find(']', left + 1)
    if left < 0 or right < 0:
        return ''

    # 기존 코드처럼 [명령어/추가내용] 중 첫 번째 항목만 사용합니다.
    key = toot_text[left + 1:right].split('/')[0].strip()

    if key == '다이스':
        return str(random.randint(1, 100))
    if key.upper() == 'YN':
        return random.choice(['YES', 'NO'])
    if key == '결과':
        return random.choice(['성공', '실패'])
    if key == '포춘쿠키':
        # 하루 1회 제한을 없앴습니다. 요청할 때마다 랜덤 문구를 지급합니다.
        if not FORTUNE_FILE.exists():
            return '포춘쿠키 메시지 파일이 없습니다.'
        messages = [line.strip() for line in FORTUNE_FILE.read_text(encoding='utf-8').splitlines() if line.strip()]
        return random.choice(messages) if messages else '포춘쿠키 메시지 파일이 비어 있습니다.'
    if key.upper().startswith('D') and key[1:].isdigit():
        dice_max = int(key[1:])
        # 비정상적으로 큰 숫자 입력을 제한합니다.
        return str(random.randint(1, dice_max)) if 1 <= dice_max <= 1_000_000 else ''
    return ''


def main():
    # 기본값은 미리보기 모드입니다. 실제 답장은 LIVE_MODE=true일 때만 발송합니다.
    live_mode = os.getenv('LIVE_MODE', 'false').lower() == 'true'
    api = Mastodon(
        client_id=os.environ['MASTODON_CLIENT_ID'],
        client_secret=os.environ['MASTODON_CLIENT_SECRET'],
        access_token=os.environ['MASTODON_ACCESS_TOKEN'],
        api_base_url=BASE,
    )
    me = api.account_verify_credentials()
    print(f'Login OK / mode={"LIVE" if live_mode else "DRY RUN"}')

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=LOOKBACK_MINUTES)

    # 5분마다 한 번씩 최근 알림을 확인합니다. 최신 80개 중 멘션만 조회합니다.
    notifications = api.notifications(limit=80, types=['mention'])
    print(f'Fetched {len(notifications)} mention notifications')
    for notice in reversed(notifications):
        status = notice.get('status')
        if not status:
            continue
        # 오래된 멘션을 다시 응답하지 않도록 시간으로 필터링합니다.
        created = notice.get('created_at') or status.get('created_at')
        if not created or created < cutoff:
            continue
        account = status['account']
        if str(account['id']) == str(me['id']):
            continue
        reply = make_reply(status.get('content', ''))
        if not reply:
            continue
        acct = account['acct']
        if live_mode:
            # 이전 코드와 동일하게 비공개(private) 답글로 보냅니다.
            # 알림을 답장 후 삭제하므로 이후 실행에서 같은 알림을 다시 처리하지 않습니다.
            api.status_post(f'@{acct} {reply}', in_reply_to_id=status['id'], visibility='private')
            # 중요: 봇 계정의 알림 목록에서도 이 멘션이 사라집니다.
            api.notifications_dismiss(notice['id'])
            print(f'Replied and dismissed notification {notice["id"]}')
        else:
            print(f'[DRY RUN] would reply to notification {notice["id"]}: {reply}')
    print('Done')


if __name__ == '__main__':
    main()
