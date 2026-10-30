"""Interface de linha de comando (CLI) do Cota Aberta."""

import argparse
import sys
from pathlib import Path

from cota_aberta.downloader import download_cvm_month
from cota_aberta.storage import FundStore


def print_audit_summary(audit: dict) -> None:
    """Exibe o resumo de auditoria da importação de forma estruturada e legível."""
    print("--------------------------------------------------")
    print("Resumo da Importação CVM:")
    print(f"  Origem:            {audit.get('source_url')}")
    print(f"  Mês de Referência: {audit.get('affected_month')}")
    print(f"  Hash do Arquivo:   {audit.get('file_hash')}")
    print(f"  Total de Linhas:   {audit.get('total_rows'):,}")
    print(f"  Linhas Válidas:    {audit.get('valid_rows'):,}")
    print(f"  Linhas Rejeitadas: {audit.get('rejected_rows'):,}")
    print(f"  Duplicadas:        {audit.get('duplicate_rows'):,}")
    print(f"  Campos Inválidos:  {audit.get('bad_fields_count'):,}")
    print(f"  Data de Ingestão:  {audit.get('imported_at')}")
    print("--------------------------------------------------")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m cota_aberta.cli",
        description="Utilitário de ingestão e gerenciamento de dados de fundos da CVM.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    cvm_parser = subparsers.add_parser(
        "import-cvm",
        help="Baixa e importa dados de um mês específico diretamente do portal da CVM.",
    )
    cvm_parser.add_argument(
        "--month",
        required=True,
        help="Mês de competência no formato YYYY-MM (ex: 2024-01).",
    )
    cvm_parser.add_argument(
        "--db",
        default="data/funds.sqlite",
        help="Caminho para o banco de dados SQLite (padrão: data/funds.sqlite).",
    )
    cvm_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Força novo download mesmo se o arquivo já existir no cache local.",
    )

    csv_parser = subparsers.add_parser(
        "import-csv",
        help="Importa um arquivo CSV local para o banco de dados.",
    )
    csv_parser.add_argument(
        "path",
        help="Caminho para o arquivo CSV de informe diário.",
    )
    csv_parser.add_argument(
        "--db",
        default="data/funds.sqlite",
        help="Caminho para o banco de dados SQLite (padrão: data/funds.sqlite).",
    )
    csv_parser.add_argument(
        "--month",
        default=None,
        help="Mês de competência esperado no formato YYYY-MM (opcional).",
    )

    demo_parser = subparsers.add_parser(
        "demo",
        help="Carrega dados de demonstração offline localizados em data/demo/inf_diario_demo.csv.",
    )
    demo_parser.add_argument(
        "--db",
        default="data/demo.sqlite",
        help="Caminho para o banco demonstrativo (padrão: data/demo.sqlite).",
    )

    args = parser.parse_args()

    try:
        store = FundStore(args.db)
        store.initialize()

        if args.command == "import-cvm":
            print(f"Baixando dados da CVM para a competência {args.month}...")
            zip_path, source_url = download_cvm_month(args.month, refresh=args.refresh)
            print(f"Processando arquivo compactado: {zip_path.name}...")
            audit = store.import_csv(zip_path, source_url=source_url, expected_month=args.month)
            print_audit_summary(audit)
            print("Importação concluída com sucesso.")

        elif args.command == "import-csv":
            target_path = Path(args.path).resolve()
            if not target_path.exists():
                print(
                    f"Erro: O arquivo informado não foi encontrado: {target_path}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"Importando arquivo local: {target_path.name}...")
            audit = store.import_csv(target_path, source_url="local", expected_month=args.month)
            print_audit_summary(audit)
            print("Importação concluída com sucesso.")

        elif args.command == "demo":
            demo_path = Path("data/demo/inf_diario_demo.csv").resolve()
            if not demo_path.exists():
                print(
                    f"Erro: Arquivo de demonstração não encontrado em {demo_path}.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"Importando base de demonstração: {demo_path.name}...")
            audit = store.import_csv(demo_path, source_url="demo")
            print_audit_summary(audit)
            print("Demonstração carregada com sucesso.")

    except Exception as error:
        print(f"Erro na execução da operação: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
