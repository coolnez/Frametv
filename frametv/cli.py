"""Command line: `frametv <command>`. Run `frametv -h` for the list."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from .config import Settings
from .domain import TVError
from .service import FrameService


def build_service(settings: Settings, demo: bool = False) -> FrameService:
    if demo:
        from .adapters.fake import FakeFrameGateway

        return FrameService(FakeFrameGateway(), settings)
    from .adapters.samsung import SamsungFrameGateway

    return FrameService(SamsungFrameGateway(settings), settings)


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="frametv", description="Управление Samsung The Frame по локальной сети")
    p.add_argument("--config", help="путь к config.json (по умолчанию ~/.frametv/config.json)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    setup = sub.add_parser("setup", help="сохранить IP/MAC телевизора и выполнить сопряжение")
    setup.add_argument("host", help="IP-адрес телевизора, например 192.168.1.50")
    setup.add_argument("--mac", help="MAC-адрес для Wake-on-LAN (проводной или Wi-Fi, смотря как подключён ТВ)")

    sub.add_parser("status", help="состояние ТВ")
    sub.add_parser("on", help="включить (Wake-on-LAN)")
    sub.add_parser("off", help="выключить полностью (не в Art Mode)")
    sub.add_parser("art", help="включить режим Art Mode")
    sub.add_parser("tv", help="выйти из Art Mode в обычный ТВ")

    key = sub.add_parser("key", help="нажать кнопку пульта: home, volup, enter ...")
    key.add_argument("key")
    key.add_argument("--hold", type=float, default=0, help="удерживать N секунд")

    sub.add_parser("apps", help="все установленные приложения")
    sub.add_parser("favorites", help="избранные приложения")
    fav_add = sub.add_parser("fav-add", help="добавить приложение в избранное")
    fav_add.add_argument("app_id")
    fav_add.add_argument("--name")
    fav_rm = sub.add_parser("fav-rm", help="убрать приложение из избранного")
    fav_rm.add_argument("app_id")
    launch = sub.add_parser("launch", help="запустить приложение (id или имя из избранного)")
    launch.add_argument("app")
    close = sub.add_parser("close", help="закрыть приложение")
    close.add_argument("app")

    art_list = sub.add_parser("art-list", help="список картин на ТВ")
    art_list.add_argument("--category", help="MY-C0002 мои фото, MY-C0004 избранное, MY-C0008 Art Store")
    art_show = sub.add_parser("art-show", help="показать картину")
    art_show.add_argument("content_id")
    art_up = sub.add_parser("art-upload", help="загрузить своё фото (jpg/png, лучше 3840x2160)")
    art_up.add_argument("file", type=Path)
    art_up.add_argument("--matte", default="none", help="паспарту, например shadowbox_polar, modern_warm")
    art_up.add_argument("--no-show", action="store_true")
    art_del = sub.add_parser("art-delete", help="удалить загруженное фото (MY_...)")
    art_del.add_argument("content_id")
    bright = sub.add_parser("brightness", help="яркость Art Mode 1..10")
    bright.add_argument("value", type=int)
    slide = sub.add_parser("slideshow", help="смена картин каждые N минут (0 = выкл)")
    slide.add_argument("minutes", type=int)
    slide.add_argument("--ordered", action="store_true", help="по порядку, а не вперемешку")
    slide.add_argument("--category", default="MY-C0002")

    serve = sub.add_parser("serve", help="веб-пульт для телефона")
    serve.add_argument("--bind", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--demo", action="store_true", help="без телевизора, на виртуальном ТВ")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    settings = Settings.load(args.config)

    try:
        if args.cmd == "setup":
            settings.host = args.host
            if args.mac:
                settings.mac = args.mac
            settings.save()
            print(f"Сохранено в {settings.path}. Подтвердите запрос «Разрешить» на экране ТВ...")
            # Any websocket call triggers the on-screen pairing prompt and stores the token.
            apps = build_service(settings).installed_apps()
            print(f"Готово: сопряжение выполнено, найдено приложений: {len(apps)}")
            return 0

        if args.cmd == "serve":
            import uvicorn

            from .api import create_app

            app = create_app(build_service(settings, demo=args.demo))
            uvicorn.run(app, host=args.bind, port=args.port)
            return 0

        svc = build_service(settings)
        match args.cmd:
            case "status":
                _print(svc.status().to_dict())
            case "on":
                _print(svc.power_on().to_dict())
            case "off":
                svc.power_off()
            case "art":
                svc.art_mode()
            case "tv":
                svc.tv_mode()
            case "key":
                svc.press(args.key, args.hold)
            case "apps":
                _print([a.to_dict() for a in svc.installed_apps()])
            case "favorites":
                _print([a.to_dict() for a in svc.favorites()])
            case "fav-add":
                _print(svc.add_favorite(args.app_id, args.name).to_dict())
            case "fav-rm":
                svc.remove_favorite(args.app_id)
            case "launch":
                _print(svc.launch(args.app).to_dict())
            case "close":
                svc.close(args.app)
            case "art-list":
                _print([a.to_dict() for a in svc.artworks(args.category)])
            case "art-show":
                svc.show_artwork(args.content_id)
            case "art-upload":
                cid = svc.upload_artwork(args.file.read_bytes(), args.file.name, args.matte, not args.no_show)
                print(cid)
            case "art-delete":
                svc.delete_artwork(args.content_id)
            case "brightness":
                svc.set_brightness(args.value)
            case "slideshow":
                svc.set_slideshow(args.minutes, not args.ordered, args.category)
    except (TVError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
