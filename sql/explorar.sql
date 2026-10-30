SELECT
    fund_id,
    MIN(date) AS primeira_data,
    MAX(date) AS ultima_data,
    COUNT(*) AS informes,
    SUM(CASE WHEN quota IS NULL OR quota <= 0 THEN 1 ELSE 0 END) AS cotas_ausentes_ou_invalidas
FROM observations
GROUP BY fund_id
ORDER BY fund_id;

SELECT
    affected_month,
    source_url,
    file_hash,
    valid_rows,
    rejected_rows,
    duplicate_rows,
    bad_fields_count,
    imported_at
FROM import_history
ORDER BY id DESC;

SELECT
    fund_id,
    SUBSTR(date, 1, 7) AS mes,
    SUM(inflow) AS captacoes_reportadas,
    SUM(outflow) AS resgates_reportados,
    SUM(inflow) - SUM(outflow) AS saldo_reportado,
    COUNT(*) AS informes,
    COUNT(inflow) AS informes_com_captacao,
    COUNT(outflow) AS informes_com_resgate
FROM observations
GROUP BY fund_id, SUBSTR(date, 1, 7)
ORDER BY fund_id, mes;
