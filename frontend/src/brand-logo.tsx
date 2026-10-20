import { usePreferences } from './preferences';

export function BrandLogo() {
    const { theme } = usePreferences();
    return <img className="brand-logo" src={theme === 'dark' ? '/brand/spi-white.png' : '/brand/spi-black.png'} alt="SPI" width={48} height={52}/>;
}
