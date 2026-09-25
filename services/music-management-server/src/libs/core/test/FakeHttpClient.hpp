/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <memory>
#include <vector>

#include "core/http/IClient.hpp"

namespace lms::core::http::tests
{
    /// Everything a FakeHttpClient was asked to send. Owned apart from the client so a test can
    /// keep reading it after handing the client to the object under test.
    struct SentRequests
    {
        std::vector<ClientGETRequestParameters> gets;
        std::vector<ClientPOSTRequestParameters> posts;
        std::vector<ClientPUTRequestParameters> puts;
        std::vector<ClientDELETERequestParameters> deletes;
        std::size_t abortCount{};
    };

    /// An IClient that sends nothing and records every request, callbacks included, so a test can
    /// inspect the payload and play MuMa's answer back through the request's own callbacks.
    class FakeHttpClient final : public IClient
    {
    public:
        explicit FakeHttpClient(std::shared_ptr<SentRequests> sent)
            : _sent{ std::move(sent) } {}

        void sendGETRequest(ClientGETRequestParameters&& request) override { _sent->gets.push_back(std::move(request)); }
        void sendPOSTRequest(ClientPOSTRequestParameters&& request) override { _sent->posts.push_back(std::move(request)); }
        void sendPUTRequest(ClientPUTRequestParameters&& request) override { _sent->puts.push_back(std::move(request)); }
        void sendDELETERequest(ClientDELETERequestParameters&& request) override { _sent->deletes.push_back(std::move(request)); }
        void abortAllRequests() override { ++_sent->abortCount; }

    private:
        std::shared_ptr<SentRequests> _sent;
    };
} // namespace lms::core::http::tests
