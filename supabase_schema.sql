-- ==============================================================================
-- SCHEMA SUPABASE PARA GARDE CLIPBOARD PARSER
-- Ejecuta este script en el SQL Editor de tu proyecto en Supabase
-- (Dashboard -> SQL Editor -> New Query -> Run)
-- ==============================================================================

-- 1. EXTENSIÓN PARA UUID (si no está activa)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. TABLA: EXTRACTIONS (Productos capturados de tiendas y proveedores)
CREATE TABLE IF NOT EXISTS public.extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id TEXT NOT NULL,
    provider_name TEXT,
    model TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    product TEXT,
    price_no_vat NUMERIC(12, 2),
    price_vat NUMERIC(12, 2),
    pvp NUMERIC(12, 2),
    attributes TEXT,
    raw_data JSONB DEFAULT '{}'::jsonb,
    source TEXT DEFAULT 'clipboard',
    captured_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_extractions_provider_model UNIQUE (provider_id, model)
);

-- Índices de búsqueda para extractions
CREATE INDEX IF NOT EXISTS idx_extractions_provider ON public.extractions(provider_id);
CREATE INDEX IF NOT EXISTS idx_extractions_model ON public.extractions(model);
CREATE INDEX IF NOT EXISTS idx_extractions_brand ON public.extractions(brand);
CREATE INDEX IF NOT EXISTS idx_extractions_category ON public.extractions(category);
CREATE INDEX IF NOT EXISTS idx_extractions_captured_at ON public.extractions(captured_at DESC);

-- 3. TABLA: STOCK_ITEMS (Inventario del almacén / ERP)
CREATE TABLE IF NOT EXISTS public.stock_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model TEXT NOT NULL UNIQUE,
    brand TEXT,
    category TEXT,
    description TEXT,
    cost_price NUMERIC(12, 2) DEFAULT 0.00,
    stock_units INTEGER DEFAULT 0,
    price_tier TEXT,
    ean TEXT,
    source_file TEXT,
    raw_data JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para stock
CREATE INDEX IF NOT EXISTS idx_stock_model ON public.stock_items(model);
CREATE INDEX IF NOT EXISTS idx_stock_brand ON public.stock_items(brand);
CREATE INDEX IF NOT EXISTS idx_stock_category ON public.stock_items(category);

-- 4. TABLA: PROVIDERS (Configuración de proveedores y expresiones regulares)
CREATE TABLE IF NOT EXISTS public.providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    regex TEXT,
    fields JSONB DEFAULT '[]'::jsonb,
    file_format TEXT DEFAULT 'csv',
    sample_text TEXT,
    labels JSONB DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. TRIGGER AUTOMÁTICO PARA ACTUALIZAR updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS trg_extractions_updated_at ON public.extractions;
CREATE TRIGGER trg_extractions_updated_at
    BEFORE UPDATE ON public.extractions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_stock_updated_at ON public.stock_items;
CREATE TRIGGER trg_stock_updated_at
    BEFORE UPDATE ON public.stock_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_providers_updated_at ON public.providers;
CREATE TRIGGER trg_providers_updated_at
    BEFORE UPDATE ON public.providers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 6. POLÍTICAS DE ACCESO (Row Level Security - RLS)
-- Habilitar RLS en todas las tablas
ALTER TABLE public.extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stock_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.providers ENABLE ROW LEVEL SECURITY;

-- Permitir lectura y escritura con clave anon o service_role
-- (Puedes restringir estas políticas según tus necesidades de producción)
DROP POLICY IF EXISTS "Permitir acceso completo a extractions con anon o service_role" ON public.extractions;
CREATE POLICY "Permitir acceso completo a extractions con anon o service_role"
    ON public.extractions FOR ALL
    TO anon, authenticated, service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Permitir acceso completo a stock con anon o service_role" ON public.stock_items;
CREATE POLICY "Permitir acceso completo a stock con anon o service_role"
    ON public.stock_items FOR ALL
    TO anon, authenticated, service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Permitir acceso completo a providers con anon o service_role" ON public.providers;
CREATE POLICY "Permitir acceso completo a providers con anon o service_role"
    ON public.providers FOR ALL
    TO anon, authenticated, service_role
    USING (true)
    WITH CHECK (true);
