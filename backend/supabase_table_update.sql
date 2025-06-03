-- SQL для обновления таблицы ai_predictions в Supabase
-- Выполните этот код в SQL Editor в Supabase Dashboard

-- Сначала посмотрим текущую структуру (для справки)
-- \d ai_predictions;

-- Добавляем новые колонки для AI предсказаний
ALTER TABLE ai_predictions 
ADD COLUMN IF NOT EXISTS confidence_score INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS risk_factors JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS key_insights JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS context_quality JSONB DEFAULT '{}'::jsonb,
ADD COLUMN IF NOT EXISTS processing_time_seconds FLOAT DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS context_chunks_used INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS value_bets JSONB DEFAULT '[]'::jsonb;

-- Изменяем существующие колонки если нужно
ALTER TABLE ai_predictions 
ALTER COLUMN chain_of_thought TYPE TEXT,
ALTER COLUMN final_prediction TYPE TEXT,
ALTER COLUMN model_version TYPE TEXT;

-- Убираем ограничение NOT NULL с некоторых полей если оно есть
ALTER TABLE ai_predictions 
ALTER COLUMN chain_of_thought DROP NOT NULL,
ALTER COLUMN final_prediction DROP NOT NULL;

-- Добавляем индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_ai_predictions_fixture_id ON ai_predictions(fixture_id);
CREATE INDEX IF NOT EXISTS idx_ai_predictions_generated_at ON ai_predictions(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_predictions_confidence ON ai_predictions(confidence_score DESC);

-- Добавляем комментарии к колонкам для документации
COMMENT ON COLUMN ai_predictions.confidence_score IS 'AI prediction confidence score (0-100)';
COMMENT ON COLUMN ai_predictions.risk_factors IS 'Array of identified risk factors for the prediction';
COMMENT ON COLUMN ai_predictions.key_insights IS 'Array of key insights that influenced the prediction';
COMMENT ON COLUMN ai_predictions.context_quality IS 'Metadata about the quality and source of context data used';
COMMENT ON COLUMN ai_predictions.processing_time_seconds IS 'Time taken to generate the prediction in seconds';
COMMENT ON COLUMN ai_predictions.context_chunks_used IS 'Number of content chunks used in the prediction';
COMMENT ON COLUMN ai_predictions.value_bets IS 'Array of identified value betting opportunities';

-- Создаем RLS политики (сначала удаляем если существуют, потом создаем)
ALTER TABLE ai_predictions ENABLE ROW LEVEL SECURITY;

-- Удаляем существующие политики если есть
DROP POLICY IF EXISTS "Allow public read access to ai_predictions" ON ai_predictions;
DROP POLICY IF EXISTS "Allow authenticated insert to ai_predictions" ON ai_predictions;
DROP POLICY IF EXISTS "Allow authenticated update to ai_predictions" ON ai_predictions;

-- Создаем новые политики
CREATE POLICY "Allow public read access to ai_predictions" 
ON ai_predictions FOR SELECT 
USING (true);

CREATE POLICY "Allow authenticated insert to ai_predictions" 
ON ai_predictions FOR INSERT 
TO authenticated 
WITH CHECK (true);

CREATE POLICY "Allow authenticated update to ai_predictions" 
ON ai_predictions FOR UPDATE 
TO authenticated 
USING (true);

-- Проверяем финальную структуру таблицы
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'ai_predictions' 
ORDER BY ordinal_position; 