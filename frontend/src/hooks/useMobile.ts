import { useState, useEffect, useCallback, useMemo } from 'react';

export interface MobileBreakpoints {
  mobile: number;
  tablet: number;
  desktop: number;
}

export interface MobileState {
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  isTouchDevice: boolean;
  isLandscape: boolean;
  isPortrait: boolean;
  screenWidth: number;
  screenHeight: number;
  deviceType: 'mobile' | 'tablet' | 'desktop';
  platform: 'ios' | 'android' | 'windows' | 'macos' | 'linux' | 'unknown';
}

const DEFAULT_BREAKPOINTS: MobileBreakpoints = {
  mobile: 640,
  tablet: 1024,
  desktop: 1280,
};

function detectPlatform(): MobileState['platform'] {
  if (typeof navigator === 'undefined') return 'unknown';
  
  const ua = navigator.userAgent.toLowerCase();
  const platform = navigator.platform?.toLowerCase() || '';

  if (/iphone|ipad|ipod/.test(ua) || /mac/.test(platform) && 'ontouchend' in document) {
    return 'ios';
  }
  if (/android/.test(ua)) {
    return 'android';
  }
  if (/win/.test(platform)) {
    return 'windows';
  }
  if (/mac/.test(platform)) {
    return 'macos';
  }
  if (/linux/.test(platform)) {
    return 'linux';
  }
  return 'unknown';
}

function detectTouchDevice(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    'ontouchstart' in window ||
    navigator.maxTouchPoints > 0 ||
    // @ts-expect-error msMaxTouchPoints is IE-specific
    navigator.msMaxTouchPoints > 0
  );
}

function getDeviceType(width: number, breakpoints: MobileBreakpoints): MobileState['deviceType'] {
  if (width < breakpoints.mobile) return 'mobile';
  if (width < breakpoints.tablet) return 'tablet';
  return 'desktop';
}

function mobileSnapshotEqual(a: MobileState, b: MobileState): boolean {
  return (
    a.isMobile === b.isMobile &&
    a.isTablet === b.isTablet &&
    a.isDesktop === b.isDesktop &&
    a.isTouchDevice === b.isTouchDevice &&
    a.isLandscape === b.isLandscape &&
    a.isPortrait === b.isPortrait &&
    a.screenWidth === b.screenWidth &&
    a.screenHeight === b.screenHeight &&
    a.deviceType === b.deviceType &&
    a.platform === b.platform
  );
}

export function useMobile(customBreakpoints?: Partial<MobileBreakpoints>): MobileState {
  const breakpoints = useMemo(
    () => ({
      ...DEFAULT_BREAKPOINTS,
      ...customBreakpoints,
    }),
    [customBreakpoints?.mobile, customBreakpoints?.tablet, customBreakpoints?.desktop],
  );

  const getState = useCallback((): MobileState => {
    if (typeof window === 'undefined') {
      return {
        isMobile: false,
        isTablet: false,
        isDesktop: true,
        isTouchDevice: false,
        isLandscape: true,
        isPortrait: false,
        screenWidth: 1920,
        screenHeight: 1080,
        deviceType: 'desktop',
        platform: 'unknown',
      };
    }

    const width = window.innerWidth;
    const height = window.innerHeight;
    const deviceType = getDeviceType(width, breakpoints);

    return {
      isMobile: deviceType === 'mobile',
      isTablet: deviceType === 'tablet',
      isDesktop: deviceType === 'desktop',
      isTouchDevice: detectTouchDevice(),
      isLandscape: width > height,
      isPortrait: height >= width,
      screenWidth: width,
      screenHeight: height,
      deviceType,
      platform: detectPlatform(),
    };
  }, [breakpoints]);

  const [state, setState] = useState<MobileState>(getState);

  useEffect(() => {
    const handleResize = () => {
      setState((prev) => {
        const next = getState();
        return mobileSnapshotEqual(prev, next) ? prev : next;
      });
    };

    const handleOrientationChange = () => {
      setTimeout(() => {
        setState((prev) => {
          const next = getState();
          return mobileSnapshotEqual(prev, next) ? prev : next;
        });
      }, 100);
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleOrientationChange);

    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleOrientationChange);
    };
  }, [getState]);

  return state;
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mediaQuery = window.matchMedia(query);
    
    const handleChange = (event: MediaQueryListEvent) => {
      setMatches(event.matches);
    };

    setMatches(mediaQuery.matches);

    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    } else {
      mediaQuery.addListener(handleChange);
      return () => mediaQuery.removeListener(handleChange);
    }
  }, [query]);

  return matches;
}

export function usePrefersDarkMode(): boolean {
  return useMediaQuery('(prefers-color-scheme: dark)');
}

export function usePrefersReducedMotion(): boolean {
  return useMediaQuery('(prefers-reduced-motion: reduce)');
}

export function useIsMobileUserAgent(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(false);

  useEffect(() => {
    if (typeof navigator === 'undefined') return;

    const ua = navigator.userAgent;
    const mobileRegex = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;
    setIsMobile(mobileRegex.test(ua));
  }, []);

  return isMobile;
}

export default useMobile;
