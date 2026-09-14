/**
 * 医生端收藏 API 契约测试：锁定 URL/method/body + toggle 响应形状。
 *   - listFavorites: GET /api/v1/favorites
 *   - removeFavorite: DELETE /api/v1/favorites/{id}
 *   - toggleFavorite: POST /api/v1/conversations/{conversationId}/favorite（无 body，
 *     2026-09-11 死页清理批补——此前 TwinChat 无收藏入口，收藏历史页恒空）
 */
import { favoritesAPI } from '../favorites';

const okResponse = (data: any = {}) => ({
  json: async () => ({ code: 0, message: 'success', data }),
});

let fetchMock: jest.Mock;

beforeEach(() => {
  fetchMock = jest.fn().mockResolvedValue(okResponse());
  (global as any).fetch = fetchMock;
});

function lastCall() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return {
    url: url as string,
    init: init as { method: string; body?: any },
  };
}

describe('favoritesAPI', () => {
  it('listFavorites 发 GET /api/v1/favorites', async () => {
    await favoritesAPI.listFavorites();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/favorites');
    expect(init.method).toBe('GET');
  });

  it('removeFavorite 发 DELETE /api/v1/favorites/3', async () => {
    await favoritesAPI.removeFavorite(3);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/favorites/3');
    expect(init.method).toBe('DELETE');
  });

  it('toggleFavorite 发 POST /api/v1/conversations/9/favorite（无 body）并透传 is_favorite', async () => {
    fetchMock.mockResolvedValue(okResponse({ is_favorite: true }));
    const res = await favoritesAPI.toggleFavorite(9);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/conversations/9/favorite');
    expect(init.method).toBe('POST');
    expect(init.body).toBeUndefined();
    expect(res.is_favorite).toBe(true);
  });
});
